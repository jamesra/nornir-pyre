"""Background spring relaxation of masked grid control points after a move."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Sequence

import numpy as np
from numpy.typing import NDArray

import nornir_imageregistration
from nornir_imageregistration.grid_layout_relax import (
    DEFAULT_PROGRESS_EVERY,
    build_fixed_mask_for_grid,
    create_grid_spacing_layout,
    four_adjacent_indices,
    propagate_masked_grid_positions,
)
from nornir_imageregistration.grid_subdivision import (
    cell_unmasked_fractions,
    source_ok_for_grid_points,
)
from nornir_imageregistration.transforms.base import IGridTransform

if TYPE_CHECKING:
    from pyre.controllers.transformcontroller import TransformController

_logger = logging.getLogger(__name__)


@dataclass
class SourcePinCache:
    """Cached source-side pin mask for a lattice-fixed grid.

    SourcePoints do not move in grid mode, so a cell that fails the source
    unmasked threshold stays free until cell size, source mask, threshold, or
    the grid itself changes. Target coverage is recomputed each wave.
    """

    source_ok: NDArray[np.bool_]
    mask_id: int | None
    cell_size: tuple[int, int]
    min_unmasked: float
    n_points: int
    grid_dims: tuple[int, int]

    def matches(
            self,
            source_mask: NDArray[np.bool_] | None,
            cell_size: NDArray[np.integer] | tuple[int, int],
            min_unmasked: float,
            n_points: int,
            grid_dims: NDArray[np.integer] | tuple[int, int],
    ) -> bool:
        """True when this cache entry is still valid for the given inputs."""
        size = (int(cell_size[0]), int(cell_size[1]))
        dims = (int(grid_dims[0]), int(grid_dims[1]))
        mask_id = None if source_mask is None else id(source_mask)
        return (
            self.mask_id == mask_id
            and self.cell_size == size
            and self.min_unmasked == float(min_unmasked)
            and self.n_points == int(n_points)
            and self.grid_dims == dims
        )


def _point_indices_on_mask(
        points: NDArray[np.floating],
        mask: NDArray[np.bool_],
) -> set[int]:
    """Return indices whose floor(YX) is outside *mask* or on a False pixel."""
    pts = np.asarray(nornir_imageregistration.EnsureNumpyArray(points))
    if pts.size == 0:
        return set()
    y = np.floor(pts[:, 0]).astype(np.int64)
    x = np.floor(pts[:, 1]).astype(np.int64)
    height, width = int(mask.shape[0]), int(mask.shape[1])
    outside = (y < 0) | (x < 0) | (y >= height) | (x >= width)
    on_mask = np.zeros(pts.shape[0], dtype=bool)
    inside = ~outside
    if np.any(inside):
        mask_arr = np.asarray(mask, dtype=bool)
        on_mask[inside] = ~mask_arr[y[inside], x[inside]]
    return {int(i) for i in np.nonzero(outside | on_mask)[0]}


def control_point_indices_on_mask(
        source_points: NDArray[np.floating],
        target_points: NDArray[np.floating],
        source_mask: NDArray[np.bool_] | None,
        target_mask: NDArray[np.bool_] | None,
) -> set[int]:
    """Indices whose source or target coordinate is outside or on a masked pixel."""
    masked: set[int] = set()
    if target_mask is not None:
        masked.update(_point_indices_on_mask(target_points, target_mask))
    if source_mask is not None:
        masked.update(_point_indices_on_mask(source_points, source_mask))
    return masked


def control_point_indices_with_insufficient_alignment_roi(
        source_points: NDArray[np.floating],
        target_points: NDArray[np.floating],
        source_mask: NDArray[np.bool_] | None,
        target_mask: NDArray[np.bool_] | None,
        alignment_area: NDArray[np.integer] | Sequence[int],
        min_unmasked: float,
) -> set[int]:
    """Indices whose alignment window has too little unmasked tissue.

    Off-image pixels count as masked. This is the cheap "is there tissue to
    measure" check for Spacebar: a control point can sit on a live pixel while
    most of the alignment ROI hangs off the mosaic edge.
    """
    area = np.asarray(alignment_area, dtype=np.int64).reshape(-1)
    if area.size < 2 or int(area[0]) <= 0 or int(area[1]) <= 0:
        return set()
    cell = (int(area[0]), int(area[1]))
    threshold = float(min_unmasked)
    insufficient: set[int] = set()
    if source_mask is not None:
        frac = cell_unmasked_fractions(source_mask, source_points, cell)
        insufficient.update(int(i) for i in np.nonzero(frac < threshold)[0])
    if target_mask is not None:
        frac = cell_unmasked_fractions(target_mask, target_points, cell)
        insufficient.update(int(i) for i in np.nonzero(frac < threshold)[0])
    return insufficient


def neighbor_seeds_for_free_points(
        free_indices: Sequence[int],
        grid_dims: NDArray[np.integer] | tuple[int, int],
) -> list[int]:
    """Return 4-neighbors of *free_indices* that are not themselves in that set.

    ``propagate_masked_grid_positions`` does not move seeds, so Spacebar on a
    masked point must seed from a neighbor for that point to relax.
    """
    rows = int(grid_dims[0])
    cols = int(grid_dims[1])
    free = {int(i) for i in free_indices}
    seeds: list[int] = []
    seen: set[int] = set()
    for index in free:
        for neighbor in four_adjacent_indices(index, rows, cols):
            if neighbor not in free and neighbor not in seen:
                seen.add(neighbor)
                seeds.append(neighbor)
    return seeds


def _as_bool_mask(image: NDArray | None) -> NDArray[np.bool_] | None:
    """Convert a mask image to bool (nonzero = unmasked). None stays None."""
    if image is None:
        return None
    arr = np.asarray(nornir_imageregistration.EnsureNumpyArray(image))
    if arr.dtype == np.bool_:
        return arr
    return arr != 0


def _tissue_mask_from_image(image: NDArray | None) -> NDArray[np.bool_] | None:
    """Treat non-zero image pixels as unmasked tissue when no STOS mask is loaded."""
    if image is None:
        return None
    arr = np.asarray(nornir_imageregistration.EnsureNumpyArray(image))
    if arr.ndim > 2:
        return np.any(arr != 0, axis=2)
    return arr != 0


def resolve_stos_masks() -> tuple[NDArray[np.bool_] | None, NDArray[np.bool_] | None]:
    """Return (source_mask, target_mask) from the current STOS config.

    Pyre's Fixed* slots hold the Source (mapped) side; Warped* hold Target
    (control). Prefer explicit mask view-models, then
    ``ImagePermutationHelper.Mask``, then a tissue mask from non-zero image
    pixels. Without that fallback, missing masks make every grid point look
    fixed and masked-neighbor relaxation never runs.
    """
    import pyre.state
    config = pyre.state.get_current_stos_config()
    if config is None:
        return None, None

    source_origin = "none"
    target_origin = "none"

    # Fixed* = Source (mapped); Warped* = Target (control) — LoadSource/LoadTarget.
    source_vm = config.FixedImageMaskViewModel
    target_vm = config.WarpedImageMaskViewModel
    source_mask = _as_bool_mask(None if source_vm is None else source_vm.Image)
    target_mask = _as_bool_mask(None if target_vm is None else target_vm.Image)
    if source_mask is not None:
        source_origin = "mask_vm"
    if target_mask is not None:
        target_origin = "mask_vm"

    if source_mask is None and config.FixedImages is not None:
        source_mask = _as_bool_mask(config.FixedImages.Mask)
        if source_mask is not None:
            source_origin = "permutations"
    if target_mask is None and config.WarpedImages is not None:
        target_mask = _as_bool_mask(config.WarpedImages.Mask)
        if target_mask is not None:
            target_origin = "permutations"

    if source_mask is None:
        source_img = None if config.SourceImageViewModel is None else config.SourceImageViewModel.Image
        if source_img is None and config.FixedImages is not None:
            source_img = config.FixedImages.Image
        source_mask = _tissue_mask_from_image(source_img)
        if source_mask is not None:
            source_origin = "image_nonzero"

    if target_mask is None:
        target_img = None if config.TargetImageViewModel is None else config.TargetImageViewModel.Image
        if target_img is None and config.WarpedImages is not None:
            target_img = config.WarpedImages.Image
        target_mask = _tissue_mask_from_image(target_img)
        if target_mask is not None:
            target_origin = "image_nonzero"

    # #region agent log
    try:
        import json
        import time
        with open(r"d:\src\git\nornir\debug-79a4da.log", "a", encoding="utf-8") as _f:
            _f.write(json.dumps({
                "sessionId": "79a4da",
                "hypothesisId": "F,G,H,I",
                "location": "masked_grid_relax.py:resolve_stos_masks",
                "message": "mask resolve provenance",
                "data": {
                    "source_origin": source_origin,
                    "target_origin": target_origin,
                    "has_source_mask": source_mask is not None,
                    "has_target_mask": target_mask is not None,
                    "source_shape": None if source_mask is None else list(source_mask.shape),
                    "target_shape": None if target_mask is None else list(target_mask.shape),
                    "mask_vm_fixed_is_none": source_vm is None,
                    "mask_vm_warped_is_none": target_vm is None,
                    "fixed_images_mask_is_none": (
                        config.FixedImages is None or config.FixedImages.Mask is None),
                    "warped_images_mask_is_none": (
                        config.WarpedImages is None or config.WarpedImages.Mask is None),
                    "runId": "post-fix",
                },
                "timestamp": int(time.time() * 1000),
            }) + "\n")
    except Exception:
        pass
    # #endregion

    return source_mask, target_mask


def resolve_min_unmasked() -> float:
    """Return masked_relax_min_unmasked from AppSettings, or the default 0.25."""
    try:
        from dependency_injector.wiring import Provide, inject
        from pyre.container import IContainer
        from pyre.settings.app import AppSettings

        @inject
        def _from_container(settings: AppSettings = Provide[IContainer.settings]) -> float:
            return float(settings.stos.grid_refine.masked_relax_min_unmasked)

        return _from_container()
    except Exception:
        return 0.25


def grid_model_or_none(controller: TransformController) -> IGridTransform | None:
    """Return the live grid transform, or None when not in grid mode."""
    model = controller.TransformModel
    if isinstance(model, IGridTransform):
        return model
    return None


def run_masked_grid_relax_wave(
        target_points: NDArray[np.floating],
        grid: nornir_imageregistration.IGrid | None = None,
        fixed_mask: NDArray[np.bool_] | None = None,
        seed_indices: list[int] | None = None,
        *,
        grid_dims: Sequence[int] | NDArray[np.integer] | None = None,
        grid_spacing: Sequence[float] | NDArray[np.floating] | None = None,
        should_cancel: Callable[[], bool] | None = None,
        on_progress: Callable[[NDArray[np.floating]], None] | None = None,
        progress_every: int = DEFAULT_PROGRESS_EVERY,
) -> NDArray[np.floating]:
    """Compute updated TargetPoints after a visit-once BFS relax from *seed_indices*.

    Pass either *grid* or both *grid_dims* and *grid_spacing*. Prefer dims/spacing
    when running off the UI thread so the worker never touches a live transform.
    """
    if fixed_mask is None or seed_indices is None:
        raise ValueError("fixed_mask and seed_indices are required")
    if grid is not None:
        dims = grid.grid_dims if grid_dims is None else grid_dims
        spacing = grid.grid_spacing if grid_spacing is None else grid_spacing
    else:
        if grid_dims is None or grid_spacing is None:
            raise ValueError("Provide grid or both grid_dims and grid_spacing")
        dims = grid_dims
        spacing = grid_spacing
    layout = create_grid_spacing_layout(target_points, dims, spacing)
    return propagate_masked_grid_positions(
        target_points=target_points,
        fixed_mask=fixed_mask,
        seed_indices=seed_indices,
        grid_dims=dims,
        grid_spacing=spacing,
        layout=layout,
        should_cancel=should_cancel,
        on_progress=on_progress,
        progress_every=progress_every,
    )


def get_or_build_source_ok(
        cache: SourcePinCache | None,
        grid: nornir_imageregistration.IGrid,
        min_unmasked: float,
        source_mask: NDArray[np.bool_] | None,
) -> tuple[NDArray[np.bool_], SourcePinCache]:
    """Return source-side pin mask, reusing *cache* when still valid."""
    source_points = np.asarray(
        nornir_imageregistration.EnsureNumpyArray(grid.SourcePoints),
        dtype=np.float64)
    n_points = int(source_points.shape[0])
    if cache is not None and cache.matches(
            source_mask, grid.cell_size, min_unmasked, n_points, grid.grid_dims):
        return cache.source_ok, cache

    source_ok = source_ok_for_grid_points(
        source_points, grid.cell_size, min_unmasked, source_mask=source_mask)
    new_cache = SourcePinCache(
        source_ok=source_ok,
        mask_id=None if source_mask is None else id(source_mask),
        cell_size=(int(grid.cell_size[0]), int(grid.cell_size[1])),
        min_unmasked=float(min_unmasked),
        n_points=n_points,
        grid_dims=(int(grid.grid_dims[0]), int(grid.grid_dims[1])),
    )
    return source_ok, new_cache


def build_fixed_mask(
        grid: nornir_imageregistration.IGrid,
        min_unmasked: float,
        source_mask: NDArray[np.bool_] | None,
        target_mask: NDArray[np.bool_] | None,
        source_ok: NDArray[np.bool_] | None = None,
) -> NDArray[np.bool_]:
    """Classify fixed vs free grid points for masked relaxation."""
    return build_fixed_mask_for_grid(
        grid,
        min_unmasked,
        source_mask=source_mask,
        target_mask=target_mask,
        source_ok=source_ok,
    )
