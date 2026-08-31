"""
Created on Oct 19, 2012

@author: u0490822
"""

from __future__ import annotations

import copy
import logging
import math
import os
import threading
from collections.abc import Callable, Iterable, Sequence

import numpy
import numpy as np
from numpy.typing import NDArray
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer, QThread

import nornir_imageregistration
from nornir_imageregistration import ImagePermutationHelper
from nornir_imageregistration import cp
from nornir_imageregistration.transforms.base import IControlPoints
from nornir_imageregistration.transforms.meshwithrbffallback import GetTransformPrewarmPool
import nornir_imageregistration.interactive_edit
import nornir_imageregistration.local_distortion_correction
import nornir_pools as pools
import pyre.qt_eventmanager
from pyre.stos_registration import normalize_rigid_transform_for_pyre_editing
from pyre.controllers.control_point_registration_queue import (
    ControlPointBusySet,
    ControlPointRegistrationQueue,
    REGISTER_BUSY_REASON,
)
from pyre.observable import ObservableSet
from pyre.controllers.tile_mesh_cache import TileMeshCpuCache
from pyre.controllers.transform_display import (
    TransformDisplayStrategy,
    TransformDrawState,
    TransformGesture,
    TileRefreshHint,
    display_strategy_for_model,
    gesture_for_interactive_edit,
)
from pyre.interfaces.eventmanager import IEventManager
from pyre.interfaces.viewtype import ViewType
from pyre.space import Space
from pyre.selection_event_data import PointPair
from pyre.qt_eventmanager import qt_post_to_main
from pyre.array_host import yx_host as _mapped_yx_host
from pyre.controllers.alignment_payload import (
    SharedImagePairRef,
    StagedImagePair,
    shared_memory_supported,
    stage_image_pair,
)

_logger = logging.getLogger(__name__)


def uses_process_pool_for_point_alignment() -> bool:
    """True when point alignment payloads can reach a pool worker as host memory.

    The active backend is not the deciding factor: alignment scoring is host-only
    (``use_gpu=False``) and pool workers force a numpy backend anyway, so a CuPy
    session is eligible once its images are staged to host shared memory. Sharing
    device buffers instead is not possible — CUDA IPC is Linux-only. Callers fall
    back to the thread pool when staging fails.
    """
    return shared_memory_supported()


def max_concurrent_point_alignments() -> int:
    """Concurrent control-point alignments allowed, sized to the executing pool.

    Registration is bounded by pool workers rather than the point count so a
    "register all" of a large mesh cannot flood the pool or starve the Qt UI
    thread. Falls back to ``cpu_count() - 1`` when the pool does not report a
    worker count.
    """
    try:
        pool = (pools.GetGlobalLocalMachinePool()
                if uses_process_pool_for_point_alignment()
                else pools.GetGlobalThreadPool())
        workers = getattr(pool, "max_workers", None)
    except Exception:
        _logger.exception("Could not read pool worker count; using CPU-based limit")
        workers = None
    if workers is None:
        workers = (os.cpu_count() or 2) - 1
    return max(1, int(workers))


def _align_control_point_from_arrays(
        transform: nornir_imageregistration.ITransform,
        source_pixels: NDArray,
        source_mask: NDArray,
        source_stats: nornir_imageregistration.ImageStats,
        target_pixels: NDArray,
        target_mask: NDArray,
        target_stats: nornir_imageregistration.ImageStats,
        alignment_area: NDArray[np.integer],
        angles_to_search: NDArray[np.floating] | None,
        target_controlpoint: NDArray[np.floating],
) -> object | None:
    """Align one control point from host arrays. Shared by both pool paths.

    Scoring is host-only (``use_gpu=False``) so CuPy Pyre does not serialize
    small FFTs on the GPU. Does not change ``GetActiveComputationLib``.
    """
    from pyre.common import either_roi_is_masked

    area = np.asarray(alignment_area, dtype=np.float64)
    if either_roi_is_masked(
            transform,
            target_mask,
            source_mask,
            target_controlpoint,
            area):
        _logger.info("Skipping point alignment: masked ROI at %s", target_controlpoint)
        return None
    return nornir_imageregistration.local_distortion_correction.AttemptAlignPoint(
        transform=transform,
        targetImage=target_pixels,
        sourceImage=source_pixels,
        target_image_stats=target_stats,
        source_image_stats=source_stats,
        target_controlpoint=target_controlpoint,
        alignmentArea=area,
        anglesToSearch=angles_to_search,
        use_gpu=False,
    )


def run_control_point_alignment(
        transform: nornir_imageregistration.ITransform,
        source_image: ImagePermutationHelper,
        target_image: ImagePermutationHelper,
        alignment_area: NDArray[np.integer],
        angles_to_search: NDArray[np.floating] | None,
        target_controlpoint: NDArray[np.floating],
) -> object | None:
    """Align one control point in this process from ``ImagePermutationHelper`` pairs."""
    return _align_control_point_from_arrays(
        transform,
        _to_numpy(source_image.ImageWithMaskAsNoise),
        source_image.BlendedMask,
        source_image.Stats,
        _to_numpy(target_image.ImageWithMaskAsNoise),
        target_image.BlendedMask,
        target_image.Stats,
        alignment_area,
        angles_to_search,
        target_controlpoint,
    )


def run_shared_control_point_alignment(
        transform: nornir_imageregistration.ITransform,
        image_pair: SharedImagePairRef,
        alignment_area: NDArray[np.integer],
        angles_to_search: NDArray[np.floating] | None,
        target_controlpoint: NDArray[np.floating],
) -> object | None:
    """Align one control point in a pool worker from a staged image pair.

    Module-level and taking only segment names so process pools can pickle it
    without copying the image pair per control point.
    """
    with image_pair.source.attach() as (source_pixels, source_mask, source_stats), \
            image_pair.target.attach() as (target_pixels, target_mask, target_stats):
        return _align_control_point_from_arrays(
            transform,
            source_pixels,
            source_mask,
            source_stats,
            target_pixels,
            target_mask,
            target_stats,
            alignment_area,
            angles_to_search,
            target_controlpoint,
        )


def warmup_alignment_process_worker() -> None:
    """Import alignment modules in a process-pool worker (picklable)."""
    import nornir_imageregistration.local_distortion_correction  # noqa: F401


def warm_alignment_process_pool() -> None:
    """Create process-pool workers and import alignment modules in each."""
    pools.GetGlobalThreadPool()
    pools.GetGlobalLocalMachinePool().warm(warmup_alignment_process_worker)


def start_alignment_process_pool_warmup() -> None:
    """Spawn LocalMachinePool workers in the background so the first Spacebar is not cold."""
    def _run() -> None:
        try:
            warm_alignment_process_pool()
        except Exception:
            _logger.exception("Failed to warm the process pool")

    threading.Thread(
        target=_run, name="pyre-process-pool-warmup", daemon=True).start()


def _to_numpy(arr: NDArray) -> NDArray:
    """Return a NumPy array, calling .get() when *arr* is a CuPy ndarray."""
    if hasattr(arr, 'get'):
        return arr.get()  # type: ignore[union-attr]
    return numpy.asarray(arr)


def CreateDefaultTransform(transform_type: nornir_imageregistration.transforms.TransformType,
                           FixedShape: NDArray | None = None,
                           WarpedShape: NDArray | None = None):
    if transform_type == nornir_imageregistration.transforms.TransformType.RIGID:
        return CreateDefaultRigidTransform(FixedShape, WarpedShape)
    elif transform_type == nornir_imageregistration.transforms.TransformType.MESH:
        return CreateDefaultMeshTransform(FixedShape, WarpedShape)
    elif transform_type == nornir_imageregistration.transforms.TransformType.GRID:
        return CreateDefaultMeshTransform(FixedShape, WarpedShape)

    raise NotImplementedError()


def CreateDefaultRigidTransform(FixedShape=None, WarpedShape=None):
    return nornir_imageregistration.transforms.CenteredSimilarity2DTransform(target_offset=(0, 0),
                                                                             source_rotation_center=(0, 0), angle=0,
                                                                             scalar=1)


def CreateDefaultMeshTransform(FixedShape=None, WarpedShape=None):
    # FixedSize = Utils.Images.GetImageSize(FixedImageFullPath)
    # WarpedSize = Utils.Images.GetImageSize(WarpedImageFullPath)

    if FixedShape is None:
        FixedShape = (512, 512)

    if WarpedShape is None:
        WarpedShape = (512, 512)

    return nornir_imageregistration.transforms.factory.CreateRigidMeshTransform(target_image_shape=FixedShape,
                                                                                source_image_shape=WarpedShape,
                                                                                rangle=0.0,
                                                                                warped_offset=(0, 0),
                                                                                flip_ud=False,
                                                                                scale=1.0)

    # alignRecord = nornir_imageregistration.AlignmentRecord(peak=(0, 0), weight=0, angle=0)
    # return alignRecord.ToImageTransform(FixedShape,
    # WarpedShape)


TransformChangedCallback = Callable[['TransformController'], None]

# Called during interactive edit (point drag) with the indices that moved.
PointMovedCallback = Callable[['TransformController', NDArray[np.integer]], None]

# Parameter order is the transform controller, the old transform, the new transform
TransformModelChangedCallback = Callable[['TransformController',
                                          nornir_imageregistration.ITransform,
                                          nornir_imageregistration.ITransform], None]

BusyPointsChangedCallback = Callable[['TransformController', frozenset[int]], None]


class TransformController:
    """
    Provides methods to edit a transform.  Once passed to a view the controller can replace the transform entirely, but
    the view is not expected to update the transform controller.
    """
    debug_id = 0
    _id: int
    _TransformModel: nornir_imageregistration.ITransform | None = None
    __OnChangeEventListeners: IEventManager[TransformChangedCallback]
    __OnTransformModelReplacedEventListeners: IEventManager[TransformModelChangedCallback]
    Debug: bool
    ShowWarped: bool
    DefaultToForwardTransform: bool
    _selected_points: set[int] = set()
    _change_event_pending: bool = False  # True while a coalesced OnChange notification is queued
    _interactive_repaint_pending: bool = False
    _point_moved_event_pending: bool = False
    _interactive_edit_depth: int = 0
    _interactive_edit_space: Space | None = None
    _display_strategy: TransformDisplayStrategy
    _tile_mesh_cache: TileMeshCpuCache
    _full_refresh_needed: bool = False
    _rbf_prewarm_generation: int = 0
    _rbf_prewarm_ready: bool = True
    _hold_composite_display_until_prewarm: bool = False
    _interactive_gesture: TransformGesture = TransformGesture.NONE
    _cached_composite_display_lookat: NDArray[np.floating] | None = None
    _cached_composite_display_bounds: nornir_imageregistration.Rectangle | None = None
    _cached_composite_lookat_src: tuple[float, float] | None = None
    _cached_composite_bounds_src: tuple[float, float, float, float] | None = None
    # Stashed target-display lookat so composite panels can rebase camera.lookat when
    # freeze lifts after registration/remesh (otherwise Transform(lookat) jumps).
    _pending_composite_display_preserve: NDArray[np.floating] | None = None
    _point_ids: NDArray[np.int64]
    _id_to_index: dict[int, int]
    _next_point_id: int = 0
    _registration_queue: ControlPointRegistrationQueue
    _busy_points: ControlPointBusySet
    __OnBusyPointsChangedListeners: IEventManager[BusyPointsChangedCallback]
    _ui_selected_points: ObservableSet[int] | None
    _registration_apply_in_progress: bool = False
    _registration_align_fn: Callable[..., object] | None = None
    _registration_source_image: ImagePermutationHelper | None = None
    _registration_target_image: ImagePermutationHelper | None = None
    _registration_alignment_area: NDArray[np.integer] | None = None
    _registration_angles: NDArray[np.floating] | None = None
    _registration_staged_pair: StagedImagePair | None = None

    @property
    def interactive_edit_in_progress(self) -> bool:
        """True while a command is performing continuous transform edits (e.g. point drag)."""
        return self._interactive_edit_depth > 0

    @property
    def rbf_prewarm_ready(self) -> bool:
        """True when an RBF instance is installed, including a stale one awaiting rebuild."""
        if self._model_has_installed_rbf(self._TransformModel):
            return True
        return self._rbf_prewarm_ready

    @property
    def tile_mesh_cache(self) -> TileMeshCpuCache:
        return self._tile_mesh_cache

    @property
    def registration_apply_in_progress(self) -> bool:
        """True while a finished registration offset is being applied to the model."""
        return self._registration_apply_in_progress

    @property
    def patch_live_tile_vertices(self) -> bool:
        """True when tile meshes should be patched from live TargetPoints (drag or apply)."""
        return self.interactive_edit_in_progress or self._registration_apply_in_progress

    def _remove_duplicates_on_point_edit(self) -> bool:
        """False during drag or registration apply so control-point indices stay stable."""
        return not (self.interactive_edit_in_progress or self._registration_apply_in_progress)

    @property
    def queued_registration_ids(self) -> frozenset[int]:
        """Session IDs waiting for or running control-point registration."""
        return self._registration_queue.queued_ids

    @property
    def registration_alignment_area(self) -> NDArray[np.integer] | None:
        """(height, width) last passed to :meth:`enqueue_point_registrations`, if any."""
        return self._registration_alignment_area

    @property
    def in_flight_registration_id(self) -> int | None:
        """Session ID of the alignment currently running, if any."""
        return self._registration_queue.in_flight_id

    @property
    def busy_point_ids(self) -> frozenset[int]:
        """Session IDs in any work queue (registration, refine, …)."""
        return self._busy_points.ids

    @property
    def busy_point_indices(self) -> frozenset[int]:
        """Row indices for :attr:`busy_point_ids` that still exist on the model."""
        indices: set[int] = set()
        for point_id in self._busy_points.ids:
            index = self._id_to_index.get(int(point_id))
            if index is not None:
                indices.add(index)
        return frozenset(indices)

    def has_ui_control_point_selection(self) -> bool:
        """True when the shared STOS selection set contains one or more points."""
        ui = self._ui_selected_points
        return ui is not None and len(ui) > 0

    def freeze_composite_display_during_point_drag(self) -> bool:
        """True when composite camera/bounds must not remap through Transform().

        Also true while control points are queued or a registration offset is
        being applied. Those jobs use CuPy on a worker thread; composite paints
        must not call Transform() on the UI thread at the same time.
        """
        return (
            (
                self.interactive_edit_in_progress
                and self._interactive_gesture == TransformGesture.CONTROL_POINT_DRAG
            )
            or self._hold_composite_display_until_prewarm
            or self._registration_apply_in_progress
            or bool(self.busy_point_ids)
        )

    def _clear_composite_display_cache(self) -> None:
        """Drop cached composite lookat/bounds so the next paint remaps through Transform().

        If a display lookat was cached (freeze / busy registration), stash it so composite
        panels can rebase ``camera.lookat`` before the next paint.
        """
        if self._cached_composite_display_lookat is not None:
            self._pending_composite_display_preserve = np.asarray(
                self._cached_composite_display_lookat, dtype=np.float64).ravel()[:2].copy()
        self._cached_composite_display_lookat = None
        self._cached_composite_display_bounds = None
        self._cached_composite_lookat_src = None
        self._cached_composite_bounds_src = None

    def consume_pending_composite_display_preserve(self) -> NDArray[np.floating] | None:
        """Return and clear a stashed composite display lookat, if any."""
        pending = self._pending_composite_display_preserve
        self._pending_composite_display_preserve = None
        return pending

    @property
    def interactive_edit_space(self) -> Space | None:
        """Which display space is being edited during an interactive drag (Source=fixed, Target=warped)."""
        return self._interactive_edit_space

    @property
    def display_strategy(self) -> TransformDisplayStrategy:
        return self._display_strategy

    def _rebind_display_strategy(self) -> None:
        """Select the display strategy for the current transform model."""
        self._display_strategy = display_strategy_for_model(self._TransformModel)
        self._display_strategy.on_model_bound(self._TransformModel)

    def resolve_draw_state(
            self,
            *,
            image_space: Space,
            view_type: ViewType | None,
            composite_source_align: bool,
            tween: float) -> TransformDrawState:
        """Resolve GPU draw uniforms via the active display strategy."""
        return self._display_strategy.resolve_draw_state(
            image_space=image_space,
            view_type=view_type,
            composite_source_align=composite_source_align,
            model=self.TransformModel,
            tween=tween,
            interactive_edit_in_progress=self.interactive_edit_in_progress,
            edit_space=self._interactive_edit_space,
        )

    def begin_gesture(
            self,
            gesture: TransformGesture,
            space: Space | None = None,
            view_type: ViewType | None = None) -> None:
        """Begin a display gesture on the active strategy."""
        self._display_strategy.begin_gesture(gesture, space, view_type)
        from pyre.controllers.transform_display import RigidDisplayStrategy

        if isinstance(self._display_strategy, RigidDisplayStrategy):
            self._display_strategy.snapshot_edit_matrices(self.TransformModel)

    def end_gesture(self) -> None:
        """End the active display gesture."""
        self._display_strategy.end_gesture()

    def reset_rigid_transform(self) -> None:
        """Reset a rigid transform to zero offset and zero angle."""
        model = self._TransformModel
        if not isinstance(model, nornir_imageregistration.IRigidTransform):
            return
        model._target_offset = np.zeros(2, dtype=np.float32)  # type: ignore[attr-defined]
        model._angle = 0.0  # type: ignore[attr-defined]
        model._source_space_center_of_rotation = np.zeros(2, dtype=np.float32)  # type: ignore[attr-defined]
        if hasattr(model, '_scalar'):
            model._scalar = 1.0  # type: ignore[attr-defined]
        if hasattr(model, '_flip_ud'):
            model._flip_ud = False  # type: ignore[attr-defined]
        update_matrix = getattr(model, '_update_transform_matrix', None)
        if update_matrix is not None:
            update_matrix()
        model.OnTransformChanged()  # type: ignore[attr-defined]
        self._display_strategy.end_gesture()
        self.FireOnChangeEvent()

    def negate_rigid_angle(self) -> None:
        """Negate the rigid registration angle in place (CS2D/ITK sign workaround)."""
        model = self._TransformModel
        if not isinstance(model, nornir_imageregistration.IRigidTransform):
            return
        model._angle = -float(model.angle)  # type: ignore[attr-defined]
        update_matrix = getattr(model, '_update_transform_matrix', None)
        if update_matrix is not None:
            update_matrix()
        model.OnTransformChanged()  # type: ignore[attr-defined]
        self._display_strategy.end_gesture()
        self.FireOnChangeEvent()

    def begin_interactive_edit(
            self,
            space: Space | None = None,
            view_type: ViewType | None = None,
            gesture: TransformGesture | None = None) -> None:
        """Mark the start of a continuous edit. Heavy display refresh is deferred until end."""
        if self._interactive_edit_depth == 0:
            self._rbf_prewarm_generation += 1
            self._hold_composite_display_until_prewarm = False
            self._interactive_edit_space = space
            resolved = gesture if gesture is not None else gesture_for_interactive_edit(
                space, view_type, self.type)
            self._interactive_gesture = resolved
            self.begin_gesture(resolved, space, view_type)
        self._interactive_edit_depth += 1
        nornir_imageregistration.interactive_edit.begin()
        self._pending_moved_indices.clear()

    def end_interactive_edit(self) -> None:
        """End continuous edit and run any deferred full refresh."""
        if self._interactive_edit_depth > 0:
            self._interactive_edit_depth -= 1
        nornir_imageregistration.interactive_edit.end()
        if self._interactive_edit_depth == 0:
            was_cp_drag = self._interactive_gesture == TransformGesture.CONTROL_POINT_DRAG
            self._interactive_edit_space = None
            self._interactive_gesture = TransformGesture.NONE
            defer_lookat = (
                was_cp_drag
                and self._full_refresh_needed
                and self._model_defers_post_drag_remesh(self._TransformModel)
            )
            if defer_lookat:
                self._hold_composite_display_until_prewarm = True
            else:
                self._clear_composite_display_cache()
            self.end_gesture()
            if self._full_refresh_needed:
                self._full_refresh_needed = False
                self._run_post_interactive_refresh()
            elif isinstance(self._TransformModel, nornir_imageregistration.IRigidTransform):
                self.FireOnChangeEvent()

    def _run_post_interactive_refresh(self) -> None:
        if self._model_needs_rbf_prewarm(self._TransformModel):
            self._queue_rbf_prewarm()
        if self._model_defers_post_drag_remesh(self._TransformModel):
            return
        self._tile_mesh_cache.clear()
        self.FireOnChangeEvent()

    def copy_points(self) -> NDArray[np.floating]:
        """Return a deep copy of control points (for undo/command snapshots)."""
        if isinstance(self.TransformModel, nornir_imageregistration.IControlPoints):
            return copy.deepcopy(self.TransformModel.points)
        return np.empty((0, 4))

    @staticmethod
    def swap_columns_to_XY(input: NDArray[np.floating]) -> NDArray[np.floating]:
        """
        OpenGL uses X,Y coordinates.  Everything in Nornir uses Y,X coordinates in numpy arrays.
        For a set of Nx4 control points used by this TransformController this function swaps the
        columns in pairs to obtain the correct X,Y coordinates for rendering.

        Every caller hands the result straight to a GL buffer, which needs it C-contiguous.
        The equivalent `input[:, [1, 0, 3, 2]]` returned a non-contiguous array, so the upload
        path had to copy it again; writing the columns into a C-ordered buffer costs the same
        and lets the upload proceed without that second pass. Measured 1.7x to 2.5x faster for
        the whole convert-swap-upload sequence at N=1000 to 20000, output bit-identical. (#170)
        """
        output = np.empty((input.shape[0], 4), dtype=input.dtype, order='C')
        output[:, 0] = input[:, 1]
        output[:, 1] = input[:, 0]
        output[:, 2] = input[:, 3]
        output[:, 3] = input[:, 2]
        return output

    @property
    def selected_points(self) -> set[int]:
        return self._selected_points

    @selected_points.setter
    def selected_points(self, value: set[int]):
        self._selected_points = value

    @property
    def width(self) -> float | None:
        if isinstance(self.TransformModel, nornir_imageregistration.IDiscreteTransform):
            return self.TransformModel.FixedBoundingBox.Width

        return None

    @property
    def height(self) -> float | None:
        if isinstance(self.TransformModel, nornir_imageregistration.IDiscreteTransform):
            return self.TransformModel.FixedBoundingBox.Height

        return None

    @property
    def NumPoints(self) -> int:
        if isinstance(self.TransformModel, nornir_imageregistration.IControlPoints):
            return self.TransformModel.points.shape[0]

        return 0

    @property
    def points(self) -> NDArray[np.floating]:
        if isinstance(self.TransformModel, nornir_imageregistration.IControlPoints):
            return _to_numpy(self.TransformModel.points)

        return np.empty((0, 4))

    @property
    def SourcePoints(self) -> NDArray[np.floating]:
        if isinstance(self.TransformModel, nornir_imageregistration.IControlPoints):
            return _to_numpy(self.TransformModel.SourcePoints)

        return np.empty((0, 2))

    @property
    def TargetPoints(self) -> NDArray[np.floating]:
        if isinstance(self.TransformModel, nornir_imageregistration.IControlPoints):
            return _to_numpy(self.TransformModel.TargetPoints)

        return np.empty((0, 2))

    @property
    def WarpedTriangles(self) -> NDArray[np.integer] | None:
        """:return: The triangulation of the source space, or None if the transform does not support triangulation"""
        if isinstance(self._TransformModel, nornir_imageregistration.ITriangulatedSourceSpace):
            return self._TransformModel.source_space_trianglulation  # type: ignore[attr-defined]
        return None

    @property
    def FixedTriangles(self) -> NDArray[np.integer] | None:
        """:return: The triangulation of the fixed space, or None if the transform does not support triangulation"""
        if isinstance(self._TransformModel, nornir_imageregistration.ITriangulatedTargetSpace):
            return self._TransformModel.target_space_trianglulation  # type: ignore[attr-defined]
        return None

    @property
    def type(self) -> nornir_imageregistration.transforms.TransformType:
        """Type of transform we are controlling"""
        return self.TransformModel.type

    @property
    def TransformModel(self) -> nornir_imageregistration.ITransform:
        """The transform this controller is editing"""
        return self._TransformModel  # type: ignore[return-value]

    @TransformModel.setter
    def TransformModel(self, value: nornir_imageregistration.ITransform | None):
        if value is not None:
            value = normalize_rigid_transform_for_pyre_editing(value)

        if self._TransformModel is value:
            # Same object may have been mutated in place (e.g. RefineTransform
            # returning the transform it was given). Still refresh views/caches.
            if value is None:
                return
            self._tile_mesh_cache.clear()
            self._queue_rbf_prewarm()
            self.FireOnChangeEvent()
            return

        if self._TransformModel is not None:
            self._TransformModel.RemoveOnChangeEventListener(self.OnTransformChanged)  # type: ignore[union-attr]

        old_transform = self._TransformModel
        self._TransformModel = value
        self._rebind_display_strategy()
        # Drop meshes from the previous transform type (e.g. rigid quads after convert-to-grid).
        self._tile_mesh_cache.clear()
        self._mint_point_ids()
        self._cancel_all_registrations()

        if self._TransformModel is not None:
            assert (isinstance(value, nornir_imageregistration.ITransformChangeEvents))
            self._TransformModel.AddOnChangeEventListener(self.OnTransformChanged)  # type: ignore[union-attr]

        self._queue_rbf_prewarm()
        self.FireOnTransformModelChangeEvent(old_transform, self._TransformModel)  # type: ignore[arg-type]
        self.FireOnChangeEvent()

    def apply_external_transform(self, value: nornir_imageregistration.ITransform) -> None:
        """Install a transform produced off the UI thread and force a full refresh.

        Registration jobs (refine grid, rotate/translate, etc.) must use this so a
        stuck coalesced-change flag or same-object return cannot leave views stale.
        """
        if value is None:
            raise ValueError("apply_external_transform requires a transform")

        # Clear coalesced-notification flags that may have been set from a
        # worker-thread OnTransformChanged (QTimer from non-GUI threads is unsafe).
        self._change_event_pending = False
        self._point_moved_event_pending = False
        self._interactive_repaint_pending = False
        self._pending_moved_indices.clear()
        self._full_refresh_needed = False

        value = normalize_rigid_transform_for_pyre_editing(value)
        old_transform = self._TransformModel

        if old_transform is not None:
            try:
                old_transform.RemoveOnChangeEventListener(self.OnTransformChanged)  # type: ignore[union-attr]
            except Exception:
                pass

        # Always take the replace path even if refine returned the same instance.
        self._TransformModel = value
        self._rebind_display_strategy()
        self._tile_mesh_cache.clear()
        self._mint_point_ids()
        self._cancel_all_registrations()

        assert isinstance(value, nornir_imageregistration.ITransformChangeEvents)
        value.AddOnChangeEventListener(self.OnTransformChanged)  # type: ignore[arg-type]

        self._queue_rbf_prewarm()
        # Pass a distinct old reference so listeners treat this as a real replace
        # even when value is the object previously installed.
        replaced_from = None if old_transform is value else old_transform
        self.FireOnTransformModelChangeEvent(replaced_from, value)  # type: ignore[arg-type]
        self.notify_views_now()

    def notify_views_now(self) -> None:
        """Deliver OnChange listeners immediately (GUI thread) or post to main."""
        app = QApplication.instance()
        if app is not None and QThread.currentThread() != app.thread():
            qt_post_to_main(self.notify_views_now)
            return
        self._change_event_pending = False
        self.__OnChangeEventListeners.invoke(self)
    def Transform(self, points: NDArray[np.floating], **kwargs):
        if self.interactive_edit_in_progress:
            # Callers such as composite lookat pass extrapolate=True; that must not
            # rebuild RBF weights on the UI thread during a control-point drag.
            kwargs['extrapolate'] = False
        elif self.freeze_composite_display_during_point_drag():
            kwargs['extrapolate'] = False
        elif not self.rbf_prewarm_ready:
            kwargs.setdefault('extrapolate', False)
        return self.TransformModel.Transform(points, **kwargs)

    def InverseTransform(self, points: NDArray[np.floating], **kwargs):
        if self.interactive_edit_in_progress:
            kwargs['extrapolate'] = False
        elif self.freeze_composite_display_during_point_drag():
            kwargs['extrapolate'] = False
        elif not self.rbf_prewarm_ready:
            kwargs.setdefault('extrapolate', False)
        return self.TransformModel.InverseTransform(points, **kwargs)

    def AddOnChangeEventListener(self, func: Callable):
        """Subscribe to be called when the transform changes in a way that a point may be mapped to a new position"""
        self.__OnChangeEventListeners.add(func)

    def RemoveOnChangeEventListener(self, func: Callable):
        """Unsubscribe to be called when the transform changes in a way that a point may be mapped to a new position"""
        self.__OnChangeEventListeners.remove(func)

    def AddOnPointMovedEventListener(self, func: PointMovedCallback):
        """Subscribe to lightweight notifications during interactive point drag."""
        self.__OnPointMovedEventListeners.add(func)

    def RemoveOnPointMovedEventListener(self, func: PointMovedCallback):
        self.__OnPointMovedEventListeners.remove(func)

    def AddOnModelReplacedEventListener(self, func: Callable):
        """Unsubscribe to be called when the entire transform model changes, for example the transform type is changed"""
        self.__OnTransformModelReplacedEventListeners.add(func)

    def RemoveOnModelReplacedEventListener(self, func: Callable):
        """Unsubscribe to be called when the entire transform model changes, for example the transform type is changed"""
        self.__OnTransformModelReplacedEventListeners.remove(func)

    def AddOnBusyPointsChanged(self, func: BusyPointsChangedCallback) -> None:
        """Subscribe to busy-set changes. Does not rebuild meshes."""
        self.__OnBusyPointsChangedListeners.add(func)

    def RemoveOnBusyPointsChanged(self, func: BusyPointsChangedCallback) -> None:
        """Unsubscribe from busy-set changes."""
        self.__OnBusyPointsChangedListeners.remove(func)

    def OnTransformChanged(self):
        # If the transform is getting complicated then use
        # InitializeDataStructures to parallelize the
        # data structure creation as much as possible
        self._reconcile_point_ids()
        suppress_remesh = self.patch_live_tile_vertices
        hint = self._display_strategy.on_model_changed(interactive=suppress_remesh)
        if hint == TileRefreshHint.FULL and suppress_remesh:
            self._full_refresh_needed = True
            return
        if hint == TileRefreshHint.NONE and suppress_remesh:
            return
        if (
                self._model_needs_rbf_prewarm(self._TransformModel)
                and not self._registration_queue_busy()
        ):
            self._queue_rbf_prewarm()
        self._tile_mesh_cache.clear()
        self.FireOnChangeEvent()

    def _record_point_moved(self, index: int | NDArray[np.integer]) -> None:
        """Track moved control point indices during interactive edit."""
        if isinstance(index, (int, np.integer)):
            self._pending_moved_indices.add(int(index))
        else:
            self._pending_moved_indices.update(int(i) for i in np.atleast_1d(index).tolist())
        if self.patch_live_tile_vertices and not self._display_strategy.uses_static_tile_quads():
            # Vertex buffers are patched during drag; remesh 8x8 samples on mouse-up.
            self._full_refresh_needed = True
        self.FireOnPointMovedEvent()

    def FireOnPointMovedEvent(self):
        """Notification for incremental display updates during drag."""
        if self.patch_live_tile_vertices or QApplication.instance() is None:
            self._point_moved_event_pending = False
            self._fire_pending_point_moved_event()
            return
        if self._point_moved_event_pending:
            return
        self._point_moved_event_pending = True
        QTimer.singleShot(0, self._fire_pending_point_moved_event)

    def _fire_pending_point_moved_event(self):
        self._point_moved_event_pending = False
        if not self._pending_moved_indices:
            return
        indices = np.array(sorted(self._pending_moved_indices), dtype=np.intp)
        self._pending_moved_indices.clear()
        self.__OnPointMovedEventListeners.invoke(self, indices)

    def FireOnChangeEvent(self):
        """Calls every function registered to be notified when the transform changes.

        Notifications are coalesced: while one is already queued we do not queue another,
        so a burst of changes (e.g. CTRL+scroll rotation firing one event per wheel notch)
        results in a single listener pass against the latest transform state per event-loop
        turn rather than one expensive pass (tile-buffer rebuild + lazy RBF solve) per notch.
        """

        app = QApplication.instance()
        if app is None:
            self.__OnChangeEventListeners.invoke(self)
            return

        # Transform change events can originate on worker threads (e.g. TranslateFixed
        # during refine). QTimer must be armed on the GUI thread or the pending flag
        # sticks and all later UI refreshes are dropped.
        if QThread.currentThread() != app.thread():
            qt_post_to_main(self.FireOnChangeEvent)
            return

        if self._change_event_pending:
            return

        self._change_event_pending = True
        QTimer.singleShot(0, self._fire_pending_change_event)
    def _fire_pending_change_event(self):
        """Deliver the coalesced OnChange notification queued by FireOnChangeEvent."""
        # Reset first so a change triggered *by* a listener queues a fresh pass instead of
        # being dropped, and so an exception in a listener cannot leave the flag stuck.
        self._change_event_pending = False
        if not self.freeze_composite_display_during_point_drag():
            self._clear_composite_display_cache()
        self.__OnChangeEventListeners.invoke(self)

    def notify_interactive_rigid_repaint(self) -> None:
        """Queue repaint of all transform view panels during rigid drag.

        Deferred to the next event-loop turn so we never re-enter paintGL on the
        panel handling the mouse drag; FireOnChangeEvent coalescing can defer too long.
        """
        if QApplication.instance() is None:
            self.__OnChangeEventListeners.invoke(self)
            return
        if self._interactive_repaint_pending:
            return
        self._interactive_repaint_pending = True
        QTimer.singleShot(0, self._fire_interactive_repaint)

    def _fire_interactive_repaint(self) -> None:
        self._interactive_repaint_pending = False
        self.__OnChangeEventListeners.invoke(self)

    def FireOnTransformModelChangeEvent(self, old: nornir_imageregistration.ITransform,
                                        new: nornir_imageregistration.ITransform):
        """Calls every function registered to be notified when the transform changes."""

        app = QApplication.instance()
        if app is None or QThread.currentThread() == app.thread():
            self._clear_composite_display_cache()
            self.__OnTransformModelReplacedEventListeners.invoke(self, old, new)
            return
        qt_post_to_main(
            lambda: self.__OnTransformModelReplacedEventListeners.invoke(self, old, new))
    @property
    def Id(self) -> int:
        """Unique ID of this transform controller"""
        return self._id

    def __str__(self):
        return f"TransformController {self.Id} {self.type}"

    def __init__(self, TransformModel: nornir_imageregistration.ITransform | None = None,
                 DefaultToForwardTransform: bool = True,
                 selected_points: ObservableSet[int] | None = None):
        """
        Constructor
        """

        self.debug_id = TransformController.debug_id
        self._id = self.debug_id
        TransformController.debug_id += 1

        self.__OnChangeEventListeners = pyre.qt_eventmanager.QtEventManager[TransformChangedCallback]()
        self.__OnPointMovedEventListeners = pyre.qt_eventmanager.QtEventManager[PointMovedCallback]()
        self.__OnTransformModelReplacedEventListeners = pyre.qt_eventmanager.QtEventManager[TransformModelChangedCallback]()
        self.__OnBusyPointsChangedListeners = pyre.qt_eventmanager.QtEventManager[BusyPointsChangedCallback]()

        self.DefaultToForwardTransform = DefaultToForwardTransform

        self._display_strategy = display_strategy_for_model(None)
        self._tile_mesh_cache = TileMeshCpuCache()
        self.Debug = False
        self.ShowWarped = False
        self._change_event_pending = False
        self._point_moved_event_pending = False
        self._interactive_edit_depth = 0
        self._interactive_edit_space = None
        self._pending_moved_indices = set()
        self._full_refresh_needed = False
        self._rbf_prewarm_generation = 0
        self._rbf_prewarm_ready = True
        self._hold_composite_display_until_prewarm = False
        self._interactive_gesture = TransformGesture.NONE
        self._cached_composite_display_lookat = None
        self._cached_composite_display_bounds = None
        self._cached_composite_lookat_src = None
        self._cached_composite_bounds_src = None
        self._pending_composite_display_preserve = None
        self._point_ids = np.empty(0, dtype=np.int64)
        self._id_to_index = {}
        self._next_point_id = 0
        self._registration_queue = ControlPointRegistrationQueue()
        self._busy_points = ControlPointBusySet()
        self._ui_selected_points = selected_points
        self._registration_apply_in_progress = False
        self._registration_align_fn = None
        self._registration_source_image = None
        self._registration_target_image = None
        self._registration_alignment_area = None
        self._registration_angles = None

        self.TransformModel = TransformModel

        if TransformModel is None:
            self.TransformModel = CreateDefaultTransform(nornir_imageregistration.transforms.TransformType.RIGID)

        # print("Create transform controller %d" % self._id)

    def _model_needs_rbf_prewarm(self, model: nornir_imageregistration.ITransform | None) -> bool:
        """True when the model may lazily build RBF weights on Transform."""
        if model is None or not hasattr(model, 'InitializeDataStructures'):
            return False
        # Do not use the ForwardRBFInstance property: getattr/hasattr would
        # construct RBF weights on this thread.
        return (
            hasattr(model, '_ForwardRBFInstance')
            or hasattr(model, '_continuous_transform')
            or callable(getattr(model, 'build_refreshed_continuous', None))
        )

    def _model_defers_post_drag_remesh(
            self, model: nornir_imageregistration.ITransform | None) -> bool:
        """True when tile remesh must wait for off-UI Delaunay/RBF install (mesh)."""
        return getattr(model, "type", None) == nornir_imageregistration.transforms.TransformType.MESH

    def _model_has_installed_rbf(
            self, model: nornir_imageregistration.ITransform | None = None) -> bool:
        """True when the live model already has a forward RBF instance (possibly stale)."""
        if model is None:
            model = self._TransformModel
        return getattr(model, '_ForwardRBFInstance', None) is not None

    def _registration_queue_busy(self) -> bool:
        """True while alignments are queued, in flight, or otherwise marked busy."""
        return (
            not self._registration_queue.is_idle
            or self.in_flight_registration_id is not None
            or bool(self.busy_point_ids)
        )

    def _queue_rbf_prewarm(self) -> None:
        """Build a replacement RBF fallback on the single prewarm thread, then install it."""
        model = self._TransformModel
        if not self._model_needs_rbf_prewarm(model):
            self._rbf_prewarm_ready = True
            return
        if self._registration_queue_busy():
            return

        has_rbf = self._model_has_installed_rbf(model)
        self._rbf_prewarm_generation += 1
        generation = self._rbf_prewarm_generation
        if not has_rbf:
            self._rbf_prewarm_ready = False
        target_model = model
        builder = getattr(target_model, "build_refreshed_continuous", None)

        def _install(new_continuous: object | None) -> None:
            if generation != self._rbf_prewarm_generation:
                return
            if self._TransformModel is not target_model:
                return
            if new_continuous is not None:
                apply = getattr(target_model, "apply_refreshed_continuous", None)
                if callable(apply):
                    apply(new_continuous)
            if not self._model_has_installed_rbf(target_model):
                return
            self._rbf_prewarm_ready = True
            self._hold_composite_display_until_prewarm = False
            self._clear_composite_display_cache()
            self._tile_mesh_cache.clear()
            # Immediate notify: FireOnChangeEvent coalescing can drop this if a
            # convert/edit notification is already queued, leaving tiles built
            # with extrapolate=False after weights exist.
            self.notify_views_now()

        def _prewarm() -> None:
            built: object | None = None
            try:
                if callable(builder):
                    built = builder()
                else:
                    target_model.InitializeDataStructures()  # type: ignore[union-attr]
            finally:
                if QApplication.instance() is None:
                    _install(built)
                else:
                    # Pool threads have no Qt event loop; QTimer.singleShot from
                    # them never delivers and the render stays on the pre-RBF mesh.
                    qt_post_to_main(_install, built)

        GetTransformPrewarmPool().add_task(
            f"RBF prewarm gen={generation}",
            _prewarm,
        )

    def ensure_rbf_ready_blocking(self) -> None:
        """Install an RBF fallback if none exists yet. Safe to call from create-point.

        A present (possibly stale) instance is used as-is. Waiting and
        ``InitializeDataStructures`` are only allowed when no instance exists.
        """
        if self._model_has_installed_rbf():
            return
        GetTransformPrewarmPool().wait_completion()
        app = QApplication.instance()
        if app is not None:
            app.processEvents()
        if self._model_has_installed_rbf():
            return
        model = self._TransformModel
        initialize = getattr(model, "InitializeDataStructures", None)
        if callable(initialize):
            initialize()

    def map_pair_for_control_point_create(
            self,
            known_space: Space,
            known_yx: NDArray[np.floating] | Sequence[float],
    ) -> PointPair:
        """Map a click in one space to a finite source/target pair for AddPoint.

        Uses the live model with ``extrapolate=True`` so a stale RBF can fill
        outside-hull queries. Does not go through :meth:`Transform`.
        """
        self.ensure_rbf_ready_blocking()
        known = _mapped_yx_host(known_yx)
        query = known.reshape(1, 2)
        model = self._TransformModel
        if model is None:
            return PointPair(target=known.copy(), source=known.copy())
        if known_space == Space.Source:
            mapped = _mapped_yx_host(model.Transform(query, extrapolate=True))
            return PointPair(target=mapped, source=known)
        mapped = _mapped_yx_host(model.InverseTransform(query, extrapolate=True))
        return PointPair(target=known, source=mapped)

    def _rebuild_id_to_index(self) -> None:
        """Rebuild the session ID → row index map from ``_point_ids``."""
        self._id_to_index = {int(point_id): index for index, point_id in enumerate(self._point_ids.tolist())}

    def _mint_point_ids(self) -> None:
        """Assign fresh session IDs for the current control-point rows."""
        count = self.NumPoints
        self._point_ids = np.arange(count, dtype=np.int64)
        self._next_point_id = count
        self._rebuild_id_to_index()

    def _reconcile_point_ids(self) -> None:
        """Keep session IDs aligned after add (append) or unexplained shrink (remint)."""
        count = self.NumPoints
        current = int(self._point_ids.shape[0])
        if count == current:
            return
        if count > current:
            extra = count - current
            new_ids = np.arange(self._next_point_id, self._next_point_id + extra, dtype=np.int64)
            self._next_point_id += extra
            self._point_ids = np.concatenate([self._point_ids, new_ids])
            self._rebuild_id_to_index()
            return
        self._mint_point_ids()
        self._cancel_all_registrations()

    def _forget_point_ids(self, point_ids: Sequence[int]) -> None:
        """Drop session IDs after a successful remove and cancel their registrations."""
        drop = {int(point_id) for point_id in point_ids}
        for point_id in drop:
            self._registration_queue.cancel(point_id)
        if drop:
            self._sync_register_busy()
        if not drop:
            return
        keep = np.array([int(point_id) not in drop for point_id in self._point_ids.tolist()], dtype=bool)
        self._point_ids = self._point_ids[keep]
        self._rebuild_id_to_index()

    def mark_busy_points(self, reason: str, point_ids: Iterable[int]) -> None:
        """Mark session IDs as busy for *reason*. Drops them from UI selection."""
        if self._busy_points.mark(reason, point_ids):
            self._drop_busy_from_selection()
            self._fire_busy_points_changed()

    def unmark_busy_points(self, reason: str, point_ids: Iterable[int]) -> None:
        """Remove session IDs from the *reason* busy bucket."""
        if self._busy_points.unmark(reason, point_ids):
            self._fire_busy_points_changed()

    def clear_busy_points(self, reason: str) -> None:
        """Clear every ID marked busy for *reason*."""
        if self._busy_points.clear(reason):
            self._fire_busy_points_changed()

    def _cancel_all_registrations(self) -> None:
        """Drop pending/in-flight registration work and sync the busy set."""
        self._registration_queue.cancel_all()
        self._sync_register_busy()

    def _sync_register_busy(self) -> None:
        """Keep the ``register`` busy reason aligned with the registration queue."""
        changed = self._busy_points.set_ids(
            REGISTER_BUSY_REASON, self._registration_queue.queued_ids)
        if changed:
            self._drop_busy_from_selection()
            self._fire_busy_points_changed()

    def _drop_busy_from_selection(self) -> None:
        """Remove busy row indices from the shared selection set."""
        busy_indices = self.busy_point_indices
        if not busy_indices:
            return
        for index in busy_indices:
            self._selected_points.discard(index)
        ui = self._ui_selected_points
        if ui is not None:
            for index in busy_indices:
                ui.discard(index)

    def _fire_busy_points_changed(self) -> None:
        """Notify busy-set listeners without rebuilding meshes."""
        app = QApplication.instance()
        if app is not None and QThread.currentThread() != app.thread():
            qt_post_to_main(self._fire_busy_points_changed)
            return
        self.__OnBusyPointsChangedListeners.invoke(self, self.busy_point_ids)

    def point_id_for_index(self, index: int) -> int | None:
        """Return the session ID for control-point row *index*, or None."""
        if index < 0 or index >= int(self._point_ids.shape[0]):
            return None
        return int(self._point_ids[index])

    def index_for_point_id(self, point_id: int) -> int | None:
        """Return the current row index for session *point_id*, or None if removed."""
        return self._id_to_index.get(int(point_id))

    def enqueue_point_registrations(
            self,
            indices: Sequence[int],
            *,
            source_image: ImagePermutationHelper | None = None,
            target_image: ImagePermutationHelper | None = None,
            alignment_area: NDArray[np.integer] | None = None,
            angles_to_search: NDArray[np.floating] | None = None,
            align_fn: Callable[..., object] | None = None,
    ) -> list[int]:
        """Queue unique control-point alignments by session ID. Returns newly queued IDs."""
        # #region agent log
        import time
        from pyre.debug_shift_space_profile import log_event, phase_timer
        _enqueue_t0 = time.perf_counter()
        # #endregion
        point_ids: list[int] = []
        with phase_timer(
                "C",
                "transformcontroller.py:enqueue_point_registrations",
                "index_to_point_id",
                index_count=len(indices),
        ):
            for index in indices:
                point_id = self.point_id_for_index(int(index))
                if point_id is not None:
                    point_ids.append(point_id)
        if align_fn is not None:
            self._registration_align_fn = align_fn
        if source_image is not None:
            self._registration_source_image = source_image
        if target_image is not None:
            self._registration_target_image = target_image
        if alignment_area is not None:
            self._registration_alignment_area = alignment_area
        if angles_to_search is not None:
            self._registration_angles = angles_to_search
        with phase_timer(
                "C",
                "transformcontroller.py:enqueue_point_registrations",
                "queue_enqueue",
                point_id_count=len(point_ids),
        ):
            added = self._registration_queue.enqueue(point_ids)
        if added:
            _logger.info("Queued control-point alignments ids=%s", added)
            with phase_timer(
                    "C",
                    "transformcontroller.py:enqueue_point_registrations",
                    "sync_register_busy",
                    added_count=len(added),
            ):
                self._sync_register_busy()
            with phase_timer(
                    "D",
                    "transformcontroller.py:enqueue_point_registrations",
                    "pump_registration_queue",
                    added_count=len(added),
            ):
                self._pump_registration_queue()
        elif point_ids:
            _logger.info(
                "Control-point alignments already pending or in flight ids=%s",
                list(point_ids),
            )
        # #region agent log
        log_event(
            hypothesis_id="C",
            location="transformcontroller.py:enqueue_point_registrations",
            message="enqueue complete",
            data={
                "index_count": len(indices),
                "point_id_count": len(point_ids),
                "added_count": len(added),
                "pending_count": len(self._registration_queue.queued_ids),
                "elapsed_ms": round((time.perf_counter() - _enqueue_t0) * 1000.0, 3),
            },
        )
        # #endregion
        return added

    def _pump_registration_queue(self) -> None:
        """Start pending alignments until the concurrency limit is reached."""
        # Read pool capacity only when work exists; the getters build global pools.
        if self._registration_queue.pending_count == 0:
            if self._registration_queue.is_idle:
                self._on_registration_queue_idle()
            return
        capacity = max_concurrent_point_alignments()
        started_any = False
        while self._registration_queue.in_flight_count < capacity:
            point_id = self._registration_queue.take_next()
            if point_id is None:
                break
            index = self.index_for_point_id(point_id)
            if index is None:
                # Point was deleted while queued; drop it and keep filling capacity.
                self._registration_queue.finish(point_id)
                self._sync_register_busy()
                continue
            self._dispatch_point_alignment(point_id, index)
            started_any = True

        if self._registration_queue.is_idle and not started_any:
            self._on_registration_queue_idle()

    def _staged_alignment_pair(
            self,
            source_image: ImagePermutationHelper,
            target_image: ImagePermutationHelper) -> StagedImagePair | None:
        """Shared-memory staging for this image pair, created once per batch.

        Returns None when staging is unavailable, which routes the caller to the
        in-process thread pool.
        """
        existing = self._registration_staged_pair
        if existing is not None and existing.matches(source_image, target_image):
            return existing
        self._release_staged_alignment_pair()
        self._registration_staged_pair = stage_image_pair(source_image, target_image)
        return self._registration_staged_pair

    def _release_staged_alignment_pair(self) -> None:
        """Free the staged segments once no alignment can still attach to them."""
        staged = self._registration_staged_pair
        if staged is None:
            return
        self._registration_staged_pair = None
        staged.close()

    def _dispatch_point_alignment(self, point_id: int, index: int) -> None:
        """Submit one already-in-flight alignment to the process or thread pool."""
        # #region agent log
        import time
        from pyre.debug_shift_space_profile import log_event, next_alignment_seq
        _pump_t0 = time.perf_counter()
        # #endregion
        snapshot_target = _mapped_yx_host(self.GetFixedPoint(index)).copy()
        source_image = self._registration_source_image
        target_image = self._registration_target_image
        alignment_area = self._registration_alignment_area
        angles = self._registration_angles
        align_fn = self._registration_align_fn
        transform = self.TransformModel
        alignment_seq = next_alignment_seq()

        def _finish(record: object | None) -> None:
            if QApplication.instance() is None:
                self._on_registration_finished(point_id, snapshot_target, record)
            else:
                qt_post_to_main(
                    lambda: self._on_registration_finished(point_id, snapshot_target, record))

        def _thread_worker() -> None:
            record: object | None = None
            # #region agent log
            _align_t0 = time.perf_counter()
            # #endregion
            try:
                _logger.info("Aligning control point id=%s", point_id)
                record = self._run_point_alignment(
                    transform=transform,
                    source_image=source_image,
                    target_image=target_image,
                    alignment_area=alignment_area,
                    angles_to_search=angles,
                    target_controlpoint=snapshot_target,
                    align_fn=align_fn,
                )
            except Exception:
                _logger.exception("Exception aligning point id %s", point_id)
            # #region agent log
            log_event(
                hypothesis_id="D",
                location="transformcontroller.py:_thread_worker",
                message="alignment finished (thread)",
                data={
                    "alignment_seq": alignment_seq,
                    "point_id": point_id,
                    "index": index,
                    "elapsed_ms": round((time.perf_counter() - _align_t0) * 1000.0, 3),
                },
            )
            # #endregion
            _finish(record)

        if QApplication.instance() is None:
            _thread_worker()
            return

        staged_pair: StagedImagePair | None = None
        if (align_fn is None
                and transform is not None
                and source_image is not None
                and target_image is not None
                and alignment_area is not None
                and uses_process_pool_for_point_alignment()):
            staged_pair = self._staged_alignment_pair(source_image, target_image)
        use_process_pool = staged_pair is not None
        pool_kind = "process" if use_process_pool else "thread"
        # #region agent log
        log_event(
            hypothesis_id="E",
            location="transformcontroller.py:_pump_registration_queue",
            message="dispatch alignment",
            data={
                "alignment_seq": alignment_seq,
                "point_id": point_id,
                "index": index,
                "pool_kind": pool_kind,
                "pending_count": self._registration_queue.pending_count,
                "in_flight_count": self._registration_queue.in_flight_count,
                "capacity": max_concurrent_point_alignments(),
                "num_points": self.NumPoints,
            },
        )
        # #endregion
        if not use_process_pool:
            pools.GetGlobalThreadPool().add_task(
                f"Align Pyre Point id={point_id}",
                _thread_worker,
            )
            # #region agent log
            log_event(
                hypothesis_id="E",
                location="transformcontroller.py:_pump_registration_queue",
                message="thread pool submit complete",
                data={
                    "alignment_seq": alignment_seq,
                    "point_id": point_id,
                    "elapsed_ms": round((time.perf_counter() - _pump_t0) * 1000.0, 3),
                },
            )
            # #endregion
            return

        assert staged_pair is not None
        _logger.info("Aligning control point id=%s on process pool", point_id)
        try:
            task = pools.GetGlobalLocalMachinePool().add_task(
                f"Align Pyre Point id={point_id}",
                run_shared_control_point_alignment,
                transform,
                staged_pair.ref,
                alignment_area,
                angles,
                snapshot_target,
            )
        except Exception:
            _logger.exception(
                "Process-pool submit failed for point id %s; using thread pool",
                point_id,
            )
            pools.GetGlobalThreadPool().add_task(
                f"Align Pyre Point id={point_id}",
                _thread_worker,
            )
            return

        def _await_process_result() -> None:
            record: object | None = None
            # #region agent log
            _wait_t0 = time.perf_counter()
            # #endregion
            try:
                record = task.wait_return()
            except Exception:
                _logger.exception("Exception aligning point id %s", point_id)
            # #region agent log
            log_event(
                hypothesis_id="E",
                location="transformcontroller.py:_await_process_result",
                message="process pool wait complete",
                data={
                    "alignment_seq": alignment_seq,
                    "point_id": point_id,
                    "index": index,
                    "wait_ms": round((time.perf_counter() - _wait_t0) * 1000.0, 3),
                },
            )
            # #endregion
            _finish(record)

        pools.GetGlobalThreadPool().add_task(
            f"Await Pyre Point id={point_id}",
            _await_process_result,
        )
        # #region agent log
        log_event(
            hypothesis_id="E",
            location="transformcontroller.py:_pump_registration_queue",
            message="process pool submit complete",
            data={
                "alignment_seq": alignment_seq,
                "point_id": point_id,
                "elapsed_ms": round((time.perf_counter() - _pump_t0) * 1000.0, 3),
            },
        )
        # #endregion

    def _run_point_alignment(
            self,
            *,
            transform: nornir_imageregistration.ITransform,
            source_image: ImagePermutationHelper | None,
            target_image: ImagePermutationHelper | None,
            alignment_area: NDArray[np.integer] | None,
            angles_to_search: NDArray[np.floating] | None,
            target_controlpoint: NDArray[np.floating],
            align_fn: Callable[..., object] | None,
    ) -> object | None:
        """Run one control-point alignment off the UI thread."""
        if align_fn is not None:
            return align_fn(
                transform=transform,
                target_controlpoint=target_controlpoint,
                alignment_area=alignment_area,
                angles_to_search=angles_to_search,
            )
        if source_image is None or target_image is None or alignment_area is None:
            _logger.warning("Skipping point alignment: missing source/target image or alignment area")
            return None
        return run_control_point_alignment(
            transform,
            source_image,
            target_image,
            alignment_area,
            angles_to_search,
            target_controlpoint,
        )

    def _on_registration_finished(
            self,
            point_id: int,
            snapshot_target: NDArray[np.floating],
            record: object | None,
    ) -> None:
        """Apply a finished alignment on the UI thread, then start the next job."""
        # #region agent log
        import time
        from pyre.debug_shift_space_profile import log_event
        _finish_t0 = time.perf_counter()
        # #endregion
        cancelled = self._registration_queue.is_cancelled(point_id)
        self._registration_queue.finish(point_id)
        self._sync_register_busy()
        if not cancelled:
            self._apply_registration_record(point_id, snapshot_target, record)
        self._pump_registration_queue()
        # #region agent log
        log_event(
            hypothesis_id="D",
            location="transformcontroller.py:_on_registration_finished",
            message="registration finished on UI thread",
            data={
                "point_id": point_id,
                "cancelled": cancelled,
                "pending_count": len(self._registration_queue.queued_ids),
                "queue_idle": self._registration_queue.is_idle,
                "elapsed_ms": round((time.perf_counter() - _finish_t0) * 1000.0, 3),
            },
        )
        # #endregion

    def _apply_registration_record(
            self,
            point_id: int,
            snapshot_target: NDArray[np.floating],
            record: object | None,
    ) -> None:
        """Move the live point if the alignment is valid and the point was not dragged."""
        index = self.index_for_point_id(point_id)
        if index is None or record is None:
            if record is None:
                _logger.info("Alignment for point id %s produced no record", point_id)
            return
        weight = getattr(record, "weight", 0)
        peak = getattr(record, "peak", None)
        if weight == 0 or peak is None:
            _logger.info("Alignment for point id %s ignored (weight=%s)", point_id, weight)
            return
        dy, dx = float(peak[0]), float(peak[1])
        if math.isnan(dx) or math.isnan(dy):
            _logger.info("Alignment for point id %s ignored (NaN peak)", point_id)
            return
        current = _mapped_yx_host(self.GetFixedPoint(index))
        if not np.allclose(current, snapshot_target, rtol=1e-5, atol=1e-3):
            _logger.info("Alignment for point id %s discarded because the point moved", point_id)
            return
        _logger.info("Applying alignment for point id %s delta=(%s, %s)", point_id, dy, dx)
        self._registration_apply_in_progress = True
        try:
            self.MovePoint(index, dx, dy, space=Space.Target)
            if self.NumPoints != int(self._point_ids.shape[0]):
                self._mint_point_ids()
                self._cancel_all_registrations()
        finally:
            self._registration_apply_in_progress = False

    def _on_registration_queue_idle(self) -> None:
        """Remesh and refresh RBF after the last queued alignment is applied."""
        self._release_staged_alignment_pair()
        self._registration_source_image = None
        self._registration_target_image = None
        self._registration_align_fn = None
        if self._full_refresh_needed:
            self._full_refresh_needed = False
            self._run_post_interactive_refresh()
            return
        if self._model_needs_rbf_prewarm(self._TransformModel):
            self._queue_rbf_prewarm()

    def SetPoints(self, points: NDArray | nornir_imageregistration.IControlPoints):
        """Set transform points to the passed array"""
        if isinstance(points, nornir_imageregistration.IControlPoints):
            points = points.points
        elif isinstance(points, np.ndarray):
            pass
        else:
            raise ValueError(f"points parameter has unexpected type: {points.__class__}")

        if isinstance(self.TransformModel, IControlPoints):
            self.TransformModel.points = points  # type: ignore[assignment]

        return

    def NextViewMode(self):
        self.ShowWarped = not self.ShowWarped

        if not self.DefaultToForwardTransform:
            self.ShowWarped = False

    def GetFixedPoint(self, index: int):
        return self.TransformModel.TargetPoints[index, :]  # type: ignore[attr-defined]

    def GetWarpedPoint(self, index: int):
        return self.TransformModel.SourcePoints[index, :]  # type: ignore[attr-defined]

    def GetWarpedPointsInRect(self, bounds: nornir_imageregistration.Rectangle):
        return self.TransformModel.GetWarpedPointsInRect(bounds)  # type: ignore[attr-defined]

    def GetFixedPointsInRect(self, bounds: nornir_imageregistration.Rectangle):
        return self.TransformModel.GetFixedPointsInRect(bounds)  # type: ignore[attr-defined]

    def NearestPoint(self, ImagePoint: NDArray[np.floating], space: Space) -> tuple[
        float | NDArray[np.floating] | None, int | NDArray[np.integer] | None]:
        if isinstance(self.TransformModel, IControlPoints):
            if space == Space.Source:
                return self.TransformModel.NearestWarpedPoint(ImagePoint)  # type: ignore[attr-defined]
            else:
                return self.TransformModel.NearestFixedPoint(ImagePoint)  # type: ignore[attr-defined]
        else:
            return None, None

    def TranslateFixed(self, offset: nornir_imageregistration.VectorLike):
        self.TransformModel.TranslateFixed(offset)  # type: ignore[attr-defined]

    def TranslateWarped(self, offset: nornir_imageregistration.VectorLike):
        self.TransformModel.TranslateWarped(offset)  # type: ignore[attr-defined]

    def Translate(self, offset: nornir_imageregistration.VectorLike, space: Space):
        if space == Space.Source:
            self.TransformModel.TranslateWarped(offset)  # type: ignore[attr-defined]
        else:
            self.TransformModel.TranslateFixed(offset)  # type: ignore[attr-defined]
        if self.interactive_edit_in_progress and isinstance(
                self._TransformModel, nornir_imageregistration.IRigidTransform):
            self._display_strategy.on_translate_step()
            self.notify_interactive_rigid_repaint()

    def Rotate(self, rangle: float, center: NDArray[np.floating] | None = None, space: Space | None = None):
        """Rotate the layer for the given display space (Source=mapped, Target=control)."""
        if self.busy_point_ids:
            return
        edit_space = space if space is not None else self._interactive_edit_space
        if edit_space is None:
            edit_space = Space.Source
        model = self._TransformModel
        if isinstance(model, nornir_imageregistration.IRigidTransform):
            # Pivots are float64 to match ScaleFixed below. These two sites hand the value
            # straight to _pin_source_point_under_mutation, which casts to float32 on entry,
            # so the dtype here is currently unobservable (0 of 200k slice-scale samples) --
            # unlike ScaleFixed, which multiplies before that boundary and so needs float64
            # to avoid double rounding. Keeping float64 means the caller stops capping
            # precision if the rigid transform ever stores more than float32. (#165)
            if edit_space == Space.Source:
                if center is not None:
                    source_pivot = np.asarray(center, dtype=np.float64).ravel()[:2]
                    model.RotateFixedAboutSourcePoint(rangle, source_pivot)  # type: ignore[attr-defined]
                else:
                    model.RotateSourcePoints(rangle, None)  # type: ignore[attr-defined]
            else:
                if center is not None:
                    source_pivot = np.asarray(center, dtype=np.float64).ravel()[:2]
                    model.RotateFixedAboutSourcePoint(rangle, source_pivot)  # type: ignore[attr-defined]
                else:
                    model.RotateFixed(rangle, None)  # type: ignore[attr-defined]
            return
        if edit_space == Space.Source:
            if isinstance(model, nornir_imageregistration.ITransformSourceRotation):
                model.RotateSourcePoints(rangle, center)  # type: ignore[attr-defined]
            else:
                raise NotImplementedError("Current transform does not support source rotation")
        elif isinstance(model, nornir_imageregistration.ITransformTargetRotation):
            model.RotateTargetPoints(-rangle, center)  # type: ignore[attr-defined]
        else:
            raise NotImplementedError("Current transform does not support rotation")

    def ScaleWarped(
            self,
            scale_factor: float,
            center: NDArray[np.floating] | None = None,
            space: Space | None = None) -> None:
        """Scale the warped layer; optional ``center`` is a source-space pivot.

        When ``center`` is set, ``ScaleWarpedAboutSourcePoint`` pins
        ``Transform(center)`` in target space (cursor-centered scale).
        Queued (busy) points and a nonempty UI selection leave the transform
        unchanged.
        """
        del space  # Kept for call-site compatibility with Rotate/Translate space routing.
        if self.busy_point_ids or self.has_ui_control_point_selection():
            return
        model = self._TransformModel
        if isinstance(model, nornir_imageregistration.transforms.CenteredSimilarity2DTransform):
            if center is not None:
                source_pivot = np.asarray(center, dtype=np.float64).ravel()[:2]
                model.ScaleWarpedAboutSourcePoint(scale_factor, source_pivot)  # type: ignore[attr-defined]
            else:
                model.ScaleWarped(scale_factor)  # type: ignore[attr-defined]
            return
        if isinstance(model, nornir_imageregistration.ITransformRelativeScaling):
            model.ScaleWarped(scale_factor)  # type: ignore[attr-defined]
            return
        raise NotImplementedError("Current transform does not support warped scaling")

    def ScaleFixed(
            self,
            scale_factor: float,
            center: NDArray[np.floating] | None = None,
            space: Space | None = None) -> None:
        """Scale target-space control points; optional ``center`` is a target-space pivot.

        ``ScaleFixed`` is origin-relative on mesh/grid models. When ``center`` is
        set, follow it with ``TranslateFixed`` so the pivot stays put.
        Queued (busy) points and a nonempty UI selection leave the transform
        unchanged.
        """
        del space  # Kept for call-site compatibility with Rotate/Translate space routing.
        if self.busy_point_ids or self.has_ui_control_point_selection():
            return
        model = self._TransformModel
        if not isinstance(model, nornir_imageregistration.ITransformRelativeScaling):
            raise NotImplementedError("Current transform does not support fixed scaling")
        model.ScaleFixed(scale_factor)
        if center is not None and isinstance(model, nornir_imageregistration.ITransformTranslation):
            pivot = np.asarray(center, dtype=np.float64).ravel()[:2]
            model.TranslateFixed(pivot * (1.0 - float(scale_factor)))

    def FlipWarped(self):
        """
        Flip the target points
        """
        if isinstance(self.TransformModel, nornir_imageregistration.ITransformFlip):
            self.TransformModel.Flip()
        else:
            print("Transform does not support flipping")

    def TryAddPoint(self, ImageX: float, ImageY: float, space: Space = Space.Source):

        if not isinstance(self.TransformModel, nornir_imageregistration.transforms.IControlPointAddRemove):
            print("transform does not support add/remove control points")
            return

        if space == Space.Source and not self.ShowWarped:
            known_space = Space.Source
        else:
            known_space = Space.Target
        pair = self.map_pair_for_control_point_create(
            known_space, np.array((ImageY, ImageX), dtype=np.float64))
        new_point_pair = [
            float(pair.target[0]), float(pair.target[1]),
            float(pair.source[0]), float(pair.source[1]),
        ]
        return self.TransformModel.AddPoint(new_point_pair)  # type: ignore[arg-type]

    def TryDeletePoint(self, ImageX: float, ImageY: float, maxDistance: float, space: Space = Space.Source):

        if not isinstance(self.TransformModel, nornir_imageregistration.transforms.IControlPointAddRemove):
            print("transform does not support add/remove control points")
            return

        NearestPoint = None
        index = None
        distance = 0

        try:
            if space == Space.Source and not self.ShowWarped:
                distance, index = self.TransformModel.NearestWarpedPoint([ImageY, ImageX])  # type: ignore[attr-defined, arg-type]
            else:
                distance, index = self.TransformModel.NearestFixedPoint([ImageY, ImageX])  # type: ignore[attr-defined, arg-type]
        except:
            pass;

        if distance > maxDistance:
            return None

        drop_ids = [] if index is None else [self.point_id_for_index(int(index))]
        self._forget_point_ids([pid for pid in drop_ids if pid is not None])
        self.TransformModel.RemovePoint(index)  # type: ignore[arg-type]
        return True

    def TryDeletePoints(self, indicies: NDArray[np.integer] | Sequence[int]):

        if not isinstance(self.TransformModel, nornir_imageregistration.transforms.IControlPointAddRemove):
            print("transform does not support add/remove control points")
            return
        index = self._ensure_numpy_friendly_index(indicies)
        drop_ids = [
            self.point_id_for_index(int(i))
            for i in np.atleast_1d(index).tolist()
        ]
        self._forget_point_ids([pid for pid in drop_ids if pid is not None])

        try:
            self.TransformModel.RemovePoint(index)
        except ValueError:
            print(f"Could not remove points {index}, does the transform have enough points remaining?")
            self._mint_point_ids()
            return False

        return True

    def RemovePoints(self, indicies: NDArray[np.integer]):
        if isinstance(self.TransformModel, nornir_imageregistration.transforms.IControlPointAddRemove):
            drop_ids = [
                self.point_id_for_index(int(i))
                for i in np.atleast_1d(self._ensure_numpy_friendly_index(indicies)).tolist()
            ]
            self._forget_point_ids([pid for pid in drop_ids if pid is not None])
            self.TransformModel.RemovePoint(indicies)

    def TryDrag(self, ImageX: float, ImageY: float, ImageDX: float, ImageDY: float, maxDistance: float,
                space: Space = Space.Source):

        NearestPoint = None
        index = None
        Distance = 0

        if not isinstance(self.TransformModel, nornir_imageregistration.IControlPoints):
            return None

        if space == Space.Source and not self.ShowWarped:
            Distance, index = self.TransformModel.NearestWarpedPoint([ImageY, ImageX])  # type: ignore[attr-defined, arg-type]
        else:
            Distance, index = self.TransformModel.NearestFixedPoint([ImageY, ImageX])  # type: ignore[attr-defined, arg-type]

        if Distance > maxDistance:
            return None

        index = self.MovePoint(index, ImageDY, ImageDX, space=space)  # type: ignore[arg-type]
        return index

    def _points_array_for_pyre_space(self, space: Space) -> NDArray[np.floating]:
        """Return control-point rows for Pyre panel space (Source=SourcePoints, Target=TargetPoints)."""
        if space == Space.Source:
            return self.TransformModel.SourcePoints  # type: ignore[attr-defined]
        return self.TransformModel.TargetPoints  # type: ignore[attr-defined]

    @staticmethod
    def _ensure_numpy_friendly_index(index: int | set[int] | NDArray[np.integer] | list[int] | Sequence[int]) -> NDArray[np.intp] | int:
        """
        Ensures that the index is a numpy array of integers or an integer
        :param index:
        :return:
        """
        if isinstance(index, int):
            return index
        elif isinstance(index, set):
            index = np.array(list(index), dtype=int)
        elif isinstance(index, list):
            index = np.array(index, dtype=int)
        elif isinstance(index, Sequence):
            index = np.array(index, dtype=int)

        # Convert to an int if we only have one index
        # This is a band-aid as I begin supporting multiple point operations
        if len(index) == 1:
            return int(index[0])

        return index  # type: ignore[return-value]

    def GetPoints(self, index: int | set[int] | NDArray[np.integer] | list[int], space: Space = Space.Source):
        NearestPoint = None
        np_index = self._ensure_numpy_friendly_index(index)

        if isinstance(np_index, np.ndarray):
            if max(np_index) > len(self.TransformModel.SourcePoints):  # type: ignore[attr-defined]
                return None
        else:
            if np_index > len(self.TransformModel.SourcePoints):  # type: ignore[attr-defined]
                return None

        return self._points_array_for_pyre_space(space)[np_index]

    def SetPoint(self, index: int, X: float, Y: float, space: Space = Space.Source) -> int | NDArray[np.integer]:
        """Sets the specified point to the new location.  If the transform does not support editing the specied space,
        the point is changed in the opposite space if possible.  Raises ValueError if the transform does not support
        editing any space"""
        original_point = np.array((Y, X))
        point = original_point

        np_index: int | NDArray[np.integer] = self._ensure_numpy_friendly_index(index)
        remove_duplicates = self._remove_duplicates_on_point_edit()

        if space == Space.Source:
            if isinstance(self.TransformModel, nornir_imageregistration.transforms.ISourceSpaceControlPointEdit):
                np_index = self.TransformModel.UpdateSourcePointsByIndex(
                    np_index, point, remove_duplicates=remove_duplicates)  # type: ignore[attr-defined]
            elif isinstance(self.TransformModel, nornir_imageregistration.transforms.ITargetSpaceControlPointEdit):
                new_target_point = self.TransformModel.Transform([point])[0]  # type: ignore[arg-type]
                np_index = self.TransformModel.UpdateTargetPointsByIndex(
                    np_index, new_target_point, remove_duplicates=remove_duplicates)  # type: ignore[attr-defined]
            else:
                raise ValueError("Transform does not support editing source points in either source or target space")
        elif space == Space.Target:
            if isinstance(self.TransformModel, nornir_imageregistration.transforms.ITargetSpaceControlPointEdit):
                np_index = self.TransformModel.UpdateTargetPointsByIndex(
                    np_index, point, remove_duplicates=remove_duplicates)  # type: ignore[attr-defined]
            elif isinstance(self.TransformModel, nornir_imageregistration.transforms.ISourceSpaceControlPointEdit):
                new_source_point = self.TransformModel.InverseTransform([point])[0]  # type: ignore[arg-type]
                np_index = self.TransformModel.UpdateSourcePointsByIndex(
                    np_index, new_source_point, remove_duplicates=remove_duplicates)  # type: ignore[attr-defined]
            else:
                raise ValueError("Transform does not support editing target points in either source or target space")
        else:
            raise ValueError(f"Unexpected value for space: {space}")

        return np_index

    def MovePoint(self, index: int | list[int] | NDArray[np.integer], ImageDX: float, ImageDY: float,
                  space: Space = Space.Source) -> int | NDArray[np.integer]:

        if not isinstance(self.TransformModel, nornir_imageregistration.transforms.IControlPoints):
            return index  # type: ignore[return-value]

        np_index = self._ensure_numpy_friendly_index(index)

        original_point = self.GetPoints(np_index, space)
        if original_point is None:
            print(f"No point found for index {np_index}")
            return index  # type: ignore[return-value]

        xp = cp.get_array_module(original_point)
        point = original_point + xp.asarray((ImageDY, ImageDX))
        remove_duplicates = self._remove_duplicates_on_point_edit()

        if space == Space.Source:
            if isinstance(self.TransformModel, nornir_imageregistration.transforms.ISourceSpaceControlPointEdit):
                np_index = self.TransformModel.UpdateSourcePointsByIndex(
                    np_index, point, remove_duplicates=remove_duplicates)  # type: ignore[attr-defined]
            else:
                if isinstance(index, Iterable):
                    if len(index) > 1:
                        raise NotImplementedError("MovePoint does not support moving multiple points, but it should")

                OldTargetPoint = \
                    self.TransformModel.Transform([[point[0] - ImageDY, point[1] - ImageDX]])[0]  # type: ignore[arg-type]
                NewTargetPoint = self.TransformModel.Transform([point])[0]  # type: ignore[arg-type]

                # Map the source-space drag into target space and apply in the same direction.
                Delta = NewTargetPoint - OldTargetPoint
                FinalPoint = self.TransformModel.TargetPoints[np_index] + Delta  # type: ignore[attr-defined]
                np_index = self.TransformModel.UpdateTargetPointsByIndex(
                    np_index, FinalPoint, remove_duplicates=remove_duplicates)  # type: ignore[attr-defined]

        else:
            if isinstance(self.TransformModel, nornir_imageregistration.transforms.ITargetSpaceControlPointEdit):
                np_index = self.TransformModel.UpdateTargetPointsByIndex(
                    np_index, point, remove_duplicates=remove_duplicates)  # type: ignore[attr-defined]
            elif isinstance(self.TransformModel, nornir_imageregistration.transforms.ISourceSpaceControlPointEdit):
                new_source_point = self.TransformModel.InverseTransform([point])[0]  # type: ignore[arg-type]
                np_index = self.TransformModel.UpdateSourcePointsByIndex(
                    np_index, new_source_point, remove_duplicates=remove_duplicates)  # type: ignore[attr-defined]
            else:
                raise ValueError("Transform does not support editing target points in either source or target space")

        if isinstance(index, Iterable) and not isinstance(np_index, Iterable):
            result = np.array([np_index], dtype=int)
        else:
            result = np_index  # type: ignore[assignment]

        if self.patch_live_tile_vertices:
            self._record_point_moved(result)
        return result
