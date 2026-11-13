"""Mesh transforms in Pyre continue past the control-point hull with the nearest hull triangle's affine.

Matches what image warping does (``assemble.write_to_target_roi_coords``) so tiles, cursor
mapping and the warped image agree outside the hull. Grid and other transform types keep
their own extrapolation; registration and builds are unaffected.
"""
from __future__ import annotations

from typing import Any

import nornir_imageregistration
import numpy as np
from nornir_imageregistration import cp
from nornir_imageregistration.transforms import hull_extrapolation
from nornir_imageregistration.transforms.transform_type import TransformType
from numpy.typing import NDArray


def uses_hull_affine(model: Any) -> bool:
    """True when *model* is a mesh whose out-of-hull mapping Pyre fills with hull affine."""
    return (model is not None
            and getattr(model, 'type', None) == TransformType.MESH
            and hull_extrapolation.supports_hull_extrapolation(model))


def map_points(model: Any, points: NDArray[np.floating], *, forward: bool, **kwargs) -> NDArray[np.floating]:
    """``model.Transform`` (*forward*) or ``InverseTransform``, with hull affine outside a mesh's hull.

    For meshes the RBF fallback is never built, so this is safe on the UI thread during a
    drag or before the RBF prewarm finishes. Other models are called unchanged.
    """
    fn = model.Transform if forward else model.InverseTransform
    if not uses_hull_affine(model):
        return fn(points, **kwargs)
    kwargs['extrapolate'] = False
    query = nornir_imageregistration.EnsurePointsAre2DArray(points)
    return _fill_outside_hull(model, query, fn(query, **kwargs), forward=forward)


def _fill_outside_hull(model: Any, query: NDArray[np.floating], mapped: NDArray[np.floating],
                       *, forward: bool) -> NDArray[np.floating]:
    xp = cp.get_array_module(mapped)
    outside = xp.isnan(mapped).any(axis=1)
    outside_host = nornir_imageregistration.EnsureNumpyArray(outside)
    if not outside_host.any():
        return mapped
    extrapolator = (hull_extrapolation.forward_extrapolator(model) if forward
                    else hull_extrapolation.inverse_extrapolator(model))
    rows = nornir_imageregistration.EnsureNumpyArray(query, dtype=np.float64)[outside_host]
    mapped = mapped.copy()
    mapped[outside] = xp.asarray(extrapolator(rows), dtype=mapped.dtype)
    return mapped


# Newton on the forward map: a mesh is affine inside a triangle, so one step lands exactly unless the
# step crosses a triangle edge; a few more cover that. 1/100 px is far below anything visible.
_FORWARD_INVERSE_MAX_STEPS = 12
_FORWARD_INVERSE_TOLERANCE = 0.01
_JACOBIAN_STEP = 1.0


def _forward_host(model: Any, source_yx: NDArray[np.floating]) -> NDArray[np.floating]:
    """``map_points(forward=True)`` for host (N, 2) points, returned on the host as float64."""
    mapped = map_points(model, source_yx, forward=True, extrapolate=True)
    return nornir_imageregistration.EnsureNumpyArray(mapped, dtype=np.float64).reshape(-1, 2)


def source_under_target(model: Any, target_yx: NDArray[np.floating],
                        initial_source_yx: NDArray[np.floating]) -> NDArray[np.floating]:
    """Source point that the forward map (the one Pyre draws with) places at *target_yx*.

    ``InverseTransform`` is fitted separately (a mesh triangulates the target points, an RBF is a second fit),
    so where the two disagree it returns a source point drawn far from the click; adding that point then moves the
    image. Starting from *initial_source_yx* (the inverse map's answer), Newton steps on the forward map with a
    finite-difference Jacobian. Where the forward map is folded or singular, the closest point found is returned.
    Host-only: one 2-float point, a few model calls.
    """
    target = np.asarray(target_yx, dtype=np.float64).reshape(2)
    source = np.asarray(initial_source_yx, dtype=np.float64).reshape(2)
    offsets = np.array([[0.0, 0.0], [_JACOBIAN_STEP, 0.0], [0.0, _JACOBIAN_STEP]])
    best_source, best_error = source.copy(), np.inf
    step_scale = 1.0
    for _ in range(_FORWARD_INVERSE_MAX_STEPS):
        mapped = _forward_host(model, source + offsets)
        if not np.all(np.isfinite(mapped)):
            break
        residual = target - mapped[0]
        error = float(np.hypot(*residual))
        if error < best_error:
            best_source, best_error = source.copy(), error
            step_scale = 1.0
        else:
            # The step crossed into a triangle with a different affine and overshot; retry a shorter step from the
            # best point so far.
            step_scale *= 0.5
            source = best_source
            mapped = _forward_host(model, source + offsets)
            residual = target - mapped[0]
        if best_error <= _FORWARD_INVERSE_TOLERANCE:
            break
        jacobian = np.column_stack(((mapped[1] - mapped[0]), (mapped[2] - mapped[0]))) / _JACOBIAN_STEP
        try:
            step = np.linalg.solve(jacobian, residual)
        except np.linalg.LinAlgError:
            break
        source = source + step_scale * step
    return best_source
