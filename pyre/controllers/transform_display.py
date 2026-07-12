"""Pluggable display strategies for Pyre transform types."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum, auto
from typing import Sequence

import numpy as np
from numpy.typing import NDArray

import nornir_imageregistration
from nornir_imageregistration.transforms.transform_type import TransformType
from pyre.interfaces.viewtype import ViewType
from pyre.space import Space


class TransformGesture(Enum):
    """Interactive gesture affecting transform display."""

    NONE = auto()
    COMPOSITE_TRANSLATE = auto()
    WARPED_TRANSLATE = auto()
    COMPOSITE_ROTATE = auto()
    CONTROL_POINT_DRAG = auto()


class TileRefreshHint(Enum):
    """How views should refresh tile buffers after model changes."""

    NONE = "none"
    INCREMENTAL = "incremental"
    FULL = "full"


@dataclass(frozen=True)
class RigidOverlayState:
    """Optional rigid shader overlay uniforms (identity when model-authoritative)."""

    interactive_native_shift: NDArray[np.floating]
    warped_display_matrix: NDArray[np.floating]
    fixed_display_matrix: NDArray[np.floating]

    @staticmethod
    def identity() -> RigidOverlayState:
        eye = np.eye(3, dtype=np.float32)
        return RigidOverlayState(
            interactive_native_shift=np.zeros(2, dtype=np.float32),
            warped_display_matrix=eye.copy(),
            fixed_display_matrix=eye.copy(),
        )


@dataclass(frozen=True)
class TransformDrawState:
    """Resolved GPU draw parameters for one image layer pass."""

    use_rigid_path: bool
    source_to_target: NDArray[np.floating] | None
    target_to_source: NDArray[np.floating] | None
    rigid_native_is_warped: bool
    rigid_fixed_warped_into_target: bool
    rigid_overlay: RigidOverlayState | None
    tween: float


class TransformDisplayStrategy(ABC):
    """Display and interactive-gesture state for one transform family."""

    @property
    @abstractmethod
    def transform_type(self) -> TransformType:
        """Transform type this strategy handles."""

    @abstractmethod
    def on_model_bound(self, model: nornir_imageregistration.ITransform | None) -> None:
        """Called when the controller binds a new transform model."""

    @abstractmethod
    def begin_gesture(
            self,
            gesture: TransformGesture,
            space: Space | None,
            view_type: ViewType | None = None) -> None:
        """Mark the start of a continuous display gesture."""

    @abstractmethod
    def end_gesture(self) -> None:
        """End gesture and rebase display state from the registration model."""

    @abstractmethod
    def on_translate_step(self) -> None:
        """Called after each rigid whole-layer translate step during a gesture."""

    @abstractmethod
    def resolve_draw_state(
            self,
            *,
            image_space: Space,
            view_type: ViewType | None,
            composite_fixed_align: bool,
            model: nornir_imageregistration.ITransform,
            tween: float,
            interactive_edit_in_progress: bool,
            edit_space: Space | None) -> TransformDrawState:
        """Return shader uniforms for one ImageTransformView draw pass."""

    @abstractmethod
    def on_model_changed(self, *, interactive: bool) -> TileRefreshHint:
        """Hint how tile buffers should refresh after registration changes."""

    @abstractmethod
    def on_point_moved(self, indices: Sequence[int]) -> TileRefreshHint:
        """Hint how tile buffers should refresh after control points move."""

    def uses_static_tile_quads(self) -> bool:
        """True when tile meshes are static quads (no Delaunay rebuild per edit)."""
        return False


class RigidDisplayStrategy(TransformDisplayStrategy):
    """Model-authoritative rigid STOS display with gesture-aware layer freeze."""

    _gesture: TransformGesture
    _edit_space: Space | None
    _matrix_at_edit_start: NDArray[np.floating] | None
    _inverse_matrix_at_edit_start: NDArray[np.floating] | None

    def __init__(self) -> None:
        self._gesture = TransformGesture.NONE
        self._edit_space = None
        self._matrix_at_edit_start = None
        self._inverse_matrix_at_edit_start = None

    @property
    def transform_type(self) -> TransformType:
        return TransformType.RIGID

    @property
    def gesture(self) -> TransformGesture:
        return self._gesture

    @property
    def edit_space(self) -> Space | None:
        return self._edit_space

    @property
    def matrix_at_edit_start(self) -> NDArray[np.floating] | None:
        return self._matrix_at_edit_start

    @property
    def inverse_matrix_at_edit_start(self) -> NDArray[np.floating] | None:
        return self._inverse_matrix_at_edit_start

    def on_model_bound(self, model: nornir_imageregistration.ITransform | None) -> None:
        self._clear_gesture_state()

    def begin_gesture(
            self,
            gesture: TransformGesture,
            space: Space | None,
            view_type: ViewType | None = None) -> None:
        """Snapshot registration matrices for non-editing layers during the gesture."""
        self._gesture = gesture
        self._edit_space = space
        self._matrix_at_edit_start = None
        self._inverse_matrix_at_edit_start = None

    def snapshot_edit_matrices(
            self,
            model: nornir_imageregistration.ITransform) -> None:
        """Store forward/inverse matrices at gesture start (called by controller)."""
        if not isinstance(model, nornir_imageregistration.IRigidTransform):
            return
        from pyre.gl_engine.shaders.texture_shader import TextureShader

        fwd, inv = TextureShader.rigid_matrices_from_transform(model)
        self._matrix_at_edit_start = fwd.astype(np.float32, copy=True)
        self._inverse_matrix_at_edit_start = inv.astype(np.float32, copy=True)

    def end_gesture(self) -> None:
        self._clear_gesture_state()

    def on_translate_step(self) -> None:
        """Translate updates registration live; no display overlay rebasing mid-gesture."""
        return

    def _clear_gesture_state(self) -> None:
        self._gesture = TransformGesture.NONE
        self._edit_space = None
        self._matrix_at_edit_start = None
        self._inverse_matrix_at_edit_start = None

    def _use_frozen_registration(
            self,
            *,
            image_space: Space,
            composite_fixed_align: bool,
            interactive_edit_in_progress: bool,
            edit_space: Space | None) -> bool:
        """True when this layer should show registration frozen at gesture start."""
        if not interactive_edit_in_progress or edit_space is None:
            return False
        if edit_space == Space.Source:
            if image_space == Space.Target and not composite_fixed_align:
                return True
            return False
        if edit_space == Space.Target:
            if image_space == Space.Source and not composite_fixed_align:
                return True
            return False
        return False

    def resolve_draw_state(
            self,
            *,
            image_space: Space,
            view_type: ViewType | None,
            composite_fixed_align: bool,
            model: nornir_imageregistration.ITransform,
            tween: float,
            interactive_edit_in_progress: bool,
            edit_space: Space | None) -> TransformDrawState:
        """Resolve rigid shader uniforms from the live model or gesture snapshot."""
        from pyre.gl_engine.shaders.texture_shader import TextureShader

        fwd, inv = TextureShader.rigid_matrices_from_transform(model)
        if self._use_frozen_registration(
                image_space=image_space,
                composite_fixed_align=composite_fixed_align,
                interactive_edit_in_progress=interactive_edit_in_progress,
                edit_space=edit_space):
            if self._matrix_at_edit_start is not None:
                fwd = self._matrix_at_edit_start
            if self._inverse_matrix_at_edit_start is not None:
                inv = self._inverse_matrix_at_edit_start

        return TransformDrawState(
            use_rigid_path=True,
            source_to_target=fwd.astype(np.float32, copy=False),
            target_to_source=inv.astype(np.float32, copy=False),
            rigid_native_is_warped=image_space == Space.Target,
            rigid_fixed_warped_into_target=composite_fixed_align,
            rigid_overlay=RigidOverlayState.identity(),
            tween=tween,
        )

    def on_model_changed(self, *, interactive: bool) -> TileRefreshHint:
        if interactive:
            return TileRefreshHint.NONE
        return TileRefreshHint.FULL

    def on_point_moved(self, indices: Sequence[int]) -> TileRefreshHint:
        return TileRefreshHint.NONE

    def uses_static_tile_quads(self) -> bool:
        return True


class MeshLikeDisplayStrategy(TransformDisplayStrategy):
    """Delaunay tile-mesh display for mesh, grid, and RBF transforms."""

    _transform_type: TransformType

    def __init__(self, transform_type: TransformType) -> None:
        if transform_type not in (TransformType.MESH, TransformType.GRID, TransformType.RBF):
            raise ValueError(f"MeshLikeDisplayStrategy does not support {transform_type}")
        self._transform_type = transform_type

    @property
    def transform_type(self) -> TransformType:
        return self._transform_type

    def on_model_bound(self, model: nornir_imageregistration.ITransform | None) -> None:
        return

    def begin_gesture(
            self,
            gesture: TransformGesture,
            space: Space | None,
            view_type: ViewType | None = None) -> None:
        return

    def end_gesture(self) -> None:
        return

    def on_translate_step(self) -> None:
        return

    def resolve_draw_state(
            self,
            *,
            image_space: Space,
            view_type: ViewType | None,
            composite_fixed_align: bool,
            model: nornir_imageregistration.ITransform,
            tween: float,
            interactive_edit_in_progress: bool,
            edit_space: Space | None) -> TransformDrawState:
        return TransformDrawState(
            use_rigid_path=False,
            source_to_target=None,
            target_to_source=None,
            rigid_native_is_warped=False,
            rigid_fixed_warped_into_target=False,
            rigid_overlay=None,
            tween=tween,
        )

    def on_model_changed(self, *, interactive: bool) -> TileRefreshHint:
        if interactive:
            return TileRefreshHint.FULL
        return TileRefreshHint.FULL

    def on_point_moved(self, indices: Sequence[int]) -> TileRefreshHint:
        return TileRefreshHint.INCREMENTAL

    def uses_static_tile_quads(self) -> bool:
        return False


class TransformDisplayStrategyRegistry:
    """Factory for display strategies keyed by transform type."""

    _rigid: RigidDisplayStrategy
    _mesh_like: dict[TransformType, MeshLikeDisplayStrategy]

    def __init__(self) -> None:
        self._rigid = RigidDisplayStrategy()
        self._mesh_like = {
            TransformType.MESH: MeshLikeDisplayStrategy(TransformType.MESH),
            TransformType.GRID: MeshLikeDisplayStrategy(TransformType.GRID),
            TransformType.RBF: MeshLikeDisplayStrategy(TransformType.RBF),
        }

    def for_model(
            self,
            model: nornir_imageregistration.ITransform | None) -> TransformDisplayStrategy:
        """Return the display strategy for a transform model."""
        if model is None:
            return self._rigid
        if isinstance(model, nornir_imageregistration.IRigidTransform):
            return self._rigid
        transform_type = model.type
        if transform_type in self._mesh_like:
            return self._mesh_like[transform_type]
        if transform_type == TransformType.RIGID:
            return self._rigid
        return self._mesh_like.get(TransformType.MESH, self._rigid)


_DEFAULT_REGISTRY = TransformDisplayStrategyRegistry()


def display_strategy_for_model(
        model: nornir_imageregistration.ITransform | None) -> TransformDisplayStrategy:
    """Return the shared registry strategy instance for a transform model."""
    return _DEFAULT_REGISTRY.for_model(model)


def gesture_for_interactive_edit(
        space: Space | None,
        view_type: ViewType | None,
        transform_type: TransformType) -> TransformGesture:
    """Map legacy begin_interactive_edit parameters to a display gesture."""
    if transform_type != TransformType.RIGID:
        return TransformGesture.CONTROL_POINT_DRAG
    if space == Space.Source:
        if view_type == ViewType.Composite:
            return TransformGesture.COMPOSITE_TRANSLATE
        return TransformGesture.COMPOSITE_TRANSLATE
    if space == Space.Target:
        return TransformGesture.WARPED_TRANSLATE
    return TransformGesture.NONE


def gesture_for_wheel_rotate(
        space: Space,
        view_type: ViewType | None,
        transform_type: TransformType) -> TransformGesture:
    """Return the gesture enum for Ctrl+scroll rotation."""
    if transform_type == TransformType.RIGID and view_type == ViewType.Composite:
        return TransformGesture.COMPOSITE_ROTATE
    return TransformGesture.NONE
