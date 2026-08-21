"""Map source-space camera state to target display space for composite rendering.

Composite display invariant
---------------------------
The composite window uses **target display space** for overlay, camera, and hit-testing.

* **Target (control) layer** — drawn in native target coordinates; static reference.
* **Source (mapped) layer** — warped into target space via the forward transform;
  moves/deforms during alignment.

For mesh, grid, and RBF transforms, control-point drags on composite use
``Space.Source`` command space but glyphs, hit-testing, and mouse deltas are
resolved in **target display space** at ``Transform(SourcePoints)``.

Rigid whole-layer translate/rotate on composite uses ``Space.Source`` commands
(``TranslateWarped`` / source rotation). During the gesture the **target** tile
layer is frozen and the **source** overlay follows the live registration
(``RigidDisplayStrategy``).
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
from numpy.typing import NDArray

import nornir_imageregistration
from pyre.controllers.transformcontroller import TransformController
from pyre.controllers.transform_display import RigidDisplayStrategy, TransformGesture
from pyre.gl_engine.shaders.texture_shader import TextureShader
from pyre.interfaces.viewtype import ViewType
from pyre.selection_event_data import PointPair
from pyre.space import Space
from pyre.ui.camera import Camera
from pyre.views.gltiles import is_rigid_transform

# Overlay shader channel mixes in compositetransformview: source magenta, target green.
COMPOSITE_SOURCE_CHANNEL_MIX = np.array([1.0, 0.0, 1.0, 1.0], dtype=np.float32)
COMPOSITE_TARGET_CHANNEL_MIX = np.array([0.0, 1.0, 0.0, 1.0], dtype=np.float32)
COMPOSITE_SOURCE_LEGEND_COLOR = "#ff00ff"
COMPOSITE_TARGET_LEGEND_COLOR = "#00ff00"


def composite_legend_rich_text() -> str:
    """Rich text for the composite view source/target color legend."""
    return (
        f'<span style="color:{COMPOSITE_SOURCE_LEGEND_COLOR}">Source</span> '
        f'<span style="color:{COMPOSITE_TARGET_LEGEND_COLOR}">Target</span>'
    )


def _as_numpy_f64(values: NDArray[np.floating] | object) -> NDArray[np.floating]:
    """Convert transform output to host float64 for Camera and Qt paths."""
    if hasattr(values, "get"):
        values = values.get()  # type: ignore[union-attr]
    return np.asarray(values, dtype=np.float64)


def apply_rigid_yx(matrix: NDArray[np.floating], point_yx: NDArray[np.floating]) -> NDArray[np.floating]:
    """Apply a 3x3 homogeneous (Y, X) rigid matrix to a (y, x) point."""
    yx_in = np.array([point_yx[0], point_yx[1], 1.0], dtype=np.float64)
    yx_out = matrix.astype(np.float64) @ yx_in
    return np.array([yx_out[0], yx_out[1]], dtype=np.float64)


def transform_visible_rectangle(
        rect: nornir_imageregistration.Rectangle,
        matrix: NDArray[np.floating]) -> nornir_imageregistration.Rectangle:
    """Return the axis-aligned bounds of a rectangle after a rigid (Y, X) transform."""
    mapped = np.array([apply_rigid_yx(matrix, corner) for corner in rect.Corners], dtype=np.float64)
    return nornir_imageregistration.Rectangle.CreateFromBounds(
        np.array([
            float(np.min(mapped[:, 0])),
            float(np.min(mapped[:, 1])),
            float(np.max(mapped[:, 0])),
            float(np.max(mapped[:, 1])),
        ]))


def transform_visible_rectangle_mesh(
        rect: nornir_imageregistration.Rectangle,
        transform_controller: TransformController,
) -> nornir_imageregistration.Rectangle:
    """Return axis-aligned bounds of a rectangle after mesh/grid forward transform."""
    bounds = np.asarray(rect.BoundingBox, dtype=np.float64).ravel()
    src_key = (float(bounds[0]), float(bounds[1]), float(bounds[2]), float(bounds[3]))
    cached = transform_controller._cached_composite_display_bounds
    if cached is not None and transform_controller._cached_composite_bounds_src == src_key:
        return cached
    if transform_controller.freeze_composite_display_during_point_drag():
        if cached is not None:
            return cached
        return rect
    corners = np.asarray(rect.Corners, dtype=np.float64)
    mapped = _as_numpy_f64(transform_controller.Transform(corners))
    result = nornir_imageregistration.Rectangle.CreateFromBounds(
        np.array([
            float(np.min(mapped[:, 0])),
            float(np.min(mapped[:, 1])),
            float(np.max(mapped[:, 0])),
            float(np.max(mapped[:, 1])),
        ]))
    transform_controller._cached_composite_display_bounds = result
    transform_controller._cached_composite_bounds_src = src_key
    return result


def inverse_transform_visible_rectangle_mesh(
        rect: nornir_imageregistration.Rectangle,
        transform_controller: TransformController,
) -> nornir_imageregistration.Rectangle:
    """Return axis-aligned bounds of a rectangle after mesh/grid inverse transform."""
    corners = np.asarray(rect.Corners, dtype=np.float64)
    mapped = _as_numpy_f64(transform_controller.InverseTransform(corners))
    return nornir_imageregistration.Rectangle.CreateFromBounds(
        np.array([
            float(np.min(mapped[:, 0])),
            float(np.min(mapped[:, 1])),
            float(np.max(mapped[:, 0])),
            float(np.max(mapped[:, 1])),
        ]))


def composite_tile_cull_rect(
        display_bounds: nornir_imageregistration.Rectangle | None,
        transform_controller: TransformController,
        image_space: Space,
        view_type: ViewType | None,
) -> nornir_imageregistration.Rectangle | None:
    """Map composite display-space bounds to native image coordinates for tile culling."""
    if display_bounds is None or view_type != ViewType.Composite:
        return display_bounds
    model = transform_controller.TransformModel
    if model is None:
        return display_bounds
    if is_rigid_transform(model):
        if image_space == Space.Source:
            _, inverse = TextureShader.rigid_matrices_from_transform(model)
            return transform_visible_rectangle(display_bounds, inverse)
        return display_bounds
    if image_space == Space.Source:
        return inverse_transform_visible_rectangle_mesh(display_bounds, transform_controller)
    return display_bounds


def forward_for_composite_view(
        transform_controller: TransformController,
        model: object,
) -> NDArray[np.floating]:
    """Forward matrix used to couple camera lookat to composite view_proj.

    During whole-layer translate gestures the view_proj must not track live
    registration translation (target layer is frozen); only shader uniforms update.
    """
    forward, _ = TextureShader.rigid_matrices_from_transform(model)
    strategy = transform_controller.display_strategy
    if isinstance(strategy, RigidDisplayStrategy):
        if strategy.gesture in (
                TransformGesture.COMPOSITE_TRANSLATE,
                TransformGesture.WARPED_TRANSLATE,
        ):
            frozen = strategy.matrix_at_edit_start
            if frozen is not None:
                return frozen
    return forward


def _transform_single_point(
        fn: Callable[..., NDArray[np.floating] | object],
        yx: NDArray[np.floating] | object,
        **kwargs,
) -> NDArray[np.floating]:
    """Apply a transform that accepts Nx2 points and return a (y, x) vector."""
    arr = _as_numpy_f64(yx).reshape(1, 2)
    return np.squeeze(_as_numpy_f64(fn(arr, **kwargs)))


def _ui_transform_point(
        transform_controller: TransformController,
        forward: bool,
        yx: NDArray[np.floating] | object,
) -> NDArray[np.floating]:
    """Map one point for camera/mouse UI; always extrapolate so NaNs do not leak."""
    fn = transform_controller.Transform if forward else transform_controller.InverseTransform
    return _transform_single_point(fn, yx, extrapolate=True)

def display_lookat_for_composite(
        camera: Camera,
        transform_controller: TransformController,
) -> NDArray[np.floating]:
    """Return the camera lookat mapped into composite target display space."""
    model = transform_controller.TransformModel
    if model is None:
        return np.asarray(camera.lookat, dtype=np.float64)
    if is_rigid_transform(model):
        view_forward = forward_for_composite_view(transform_controller, model)
        return apply_rigid_yx(view_forward, camera.lookat)
    lookat = np.asarray(camera.lookat, dtype=np.float64).ravel()[:2]
    src_key = (float(lookat[0]), float(lookat[1]))
    cached = transform_controller._cached_composite_display_lookat
    if cached is not None and transform_controller._cached_composite_lookat_src == src_key:
        return cached
    if transform_controller.freeze_composite_display_during_point_drag():
        if cached is not None:
            return cached
        return lookat.copy()
    result = _ui_transform_point(transform_controller, True, lookat)
    transform_controller._cached_composite_display_lookat = result
    transform_controller._cached_composite_lookat_src = src_key
    return result


def lookat_from_display_position(
        transform_controller: TransformController,
        display_yx: NDArray[np.floating],
) -> NDArray[np.floating]:
    """Map a composite display-space (y,x) position back to source-camera lookat."""
    return _ui_transform_point(transform_controller, False, display_yx)

def rebase_composite_camera_after_rigid_gesture(
        camera: Camera,
        transform_controller: TransformController,
) -> None:
    """Keep composite target-display framing stable when a rigid gesture ends.

    During COMPOSITE_TRANSLATE the view_proj uses the frozen forward matrix while
    ``camera.lookat`` stays in source space. Clearing the freeze without rebasing
    makes ``Transform(lookat)`` jump, so the view snaps onto the moved source
    instead of staying locked to the target reference.
    """
    model = transform_controller.TransformModel
    if model is None or not is_rigid_transform(model):
        return
    display_yx = display_lookat_for_composite(camera, transform_controller)
    camera.lookat = lookat_from_display_position(transform_controller, display_yx)


def visible_rectangle_around_lookat(
        lookat_yx: NDArray[np.floating],
        scale: float,
        height: int,
        width: int,
) -> nornir_imageregistration.Rectangle:
    """Axis-aligned world rectangle for an orthographic camera at ``lookat_yx``."""
    half_y = (float(height) / float(scale)) / 2.0
    half_x = (float(width) / float(scale)) / 2.0
    y = float(np.asarray(lookat_yx, dtype=np.float64).ravel()[0])
    x = float(np.asarray(lookat_yx, dtype=np.float64).ravel()[1])
    return nornir_imageregistration.Rectangle.CreateFromBounds(
        np.array([y - half_y, x - half_x, y + half_y, x + half_x], dtype=np.float64))


def resolve_composite_display_draw_params(
        camera: Camera,
        transform_controller: TransformController,
        client_size: tuple[int, int],
) -> tuple[NDArray[np.floating], nornir_imageregistration.Rectangle]:
    """Return view_proj and visible bounds in target display space for composite FBO draws."""
    height, width = client_size
    model = transform_controller.TransformModel
    if model is None:
        return camera.view_proj, camera.VisibleImageBoundingBox

    display_lookat = display_lookat_for_composite(camera, transform_controller)
    view_proj = camera.view_proj_for_lookat(display_lookat, width, height)
    if is_rigid_transform(model):
        view_forward = forward_for_composite_view(transform_controller, model)
        display_bounds = transform_visible_rectangle(camera.VisibleImageBoundingBox, view_forward)
    elif transform_controller.freeze_composite_display_during_point_drag():
        display_bounds = visible_rectangle_around_lookat(display_lookat, camera.scale, height, width)
    else:
        display_bounds = transform_visible_rectangle_mesh(
            camera.VisibleImageBoundingBox, transform_controller)
    return view_proj, display_bounds


def apply_rigid_linear_delta(
        matrix: NDArray[np.floating],
        delta_yx: NDArray[np.floating]) -> NDArray[np.floating]:
    """Apply the 2x2 linear part of a rigid 3x3 matrix to a (y,x) delta."""
    linear = matrix[:2, :2].astype(np.float64)
    delta = np.asarray(delta_yx, dtype=np.float64).ravel()[:2]
    return (linear @ delta).astype(np.float64)


def lookat_delta_from_display_delta(
        model: object,
        delta_display: NDArray[np.floating]) -> NDArray[np.floating]:
    """Map a target-display-space delta to a source-camera lookat delta."""
    _, inverse = TextureShader.rigid_matrices_from_transform(model)
    return apply_rigid_linear_delta(inverse, delta_display)


def _translate_display_rectangle(
        rect: nornir_imageregistration.Rectangle,
        delta_yx: NDArray[np.floating],
) -> nornir_imageregistration.Rectangle:
    """Shift a display-space rectangle by ``delta_yx`` (MinY, MinX, MaxY, MaxX)."""
    box = np.asarray(rect.BoundingBox, dtype=np.float64).copy()
    dy, dx = float(delta_yx[0]), float(delta_yx[1])
    box[0] += dy
    box[1] += dx
    box[2] += dy
    box[3] += dx
    return nornir_imageregistration.Rectangle.CreateFromBounds(box)


def _pan_frozen_mesh_composite_display(
        camera: Camera,
        transform_controller: TransformController,
        delta: NDArray[np.floating],
) -> None:
    """Pan while Transform() is frozen: shift the cached display lookat, not InverseTransform.

    InverseTransform(cached + delta) every mouse move leaves the cache stuck (images
    do not move) and chatters ``camera.lookat`` (control points jitter).
    """
    cached = transform_controller._cached_composite_display_lookat
    if cached is None:
        cached = np.asarray(camera.lookat, dtype=np.float64).ravel()[:2]
    new_display = np.asarray(cached, dtype=np.float64).ravel()[:2] + delta
    transform_controller._cached_composite_display_lookat = new_display
    bounds = transform_controller._cached_composite_display_bounds
    if bounds is not None:
        transform_controller._cached_composite_display_bounds = _translate_display_rectangle(
            bounds, delta)
    camera.translate(delta)
    lookat = np.asarray(camera.lookat, dtype=np.float64).ravel()[:2]
    transform_controller._cached_composite_lookat_src = (float(lookat[0]), float(lookat[1]))


def apply_composite_display_pan_delta(
        camera: Camera,
        transform_controller: TransformController,
        delta_display: NDArray[np.floating],
) -> None:
    """Pan the composite camera so display space shifts by ``delta_display``."""
    model = transform_controller.TransformModel
    delta = np.asarray(delta_display, dtype=np.float64).ravel()[:2]
    if model is None:
        camera.translate(delta)
        return
    if is_rigid_transform(model):
        camera.translate(lookat_delta_from_display_delta(model, delta))
        return
    if transform_controller.freeze_composite_display_during_point_drag():
        _pan_frozen_mesh_composite_display(camera, transform_controller, delta)
        return
    current_display = display_lookat_for_composite(camera, transform_controller)
    camera.lookat = lookat_from_display_position(
        transform_controller, current_display + delta)


def display_mouse_coords(
        camera: Camera,
        transform_controller: TransformController,
        y: float,
        x: float) -> NDArray[np.floating] | None:
    """Return world (y,x) under the cursor in composite target display space."""
    model = transform_controller.TransformModel
    if model is None:
        return None
    display_lookat = display_lookat_for_composite(camera, transform_controller)
    return camera.image_coords_for_lookat(display_lookat, y, x)


def world_point_pair_for_composite_mouse(
        camera: Camera,
        transform_controller: TransformController,
        y: float,
        x: float,
) -> PointPair | None:
    """Map mouse coords to display-aligned source/target points for composite STOS."""
    display_pos = display_mouse_coords(camera, transform_controller, y, x)
    if display_pos is None:
        return None
    display_yx = _as_numpy_f64(display_pos)
    if not np.all(np.isfinite(display_yx)):
        return None
    if transform_controller.freeze_composite_display_during_point_drag():
        source_pos = display_yx
    else:
        source_pos = _ui_transform_point(transform_controller, False, display_yx)
    return PointPair(
        target=display_yx,
        source=_as_numpy_f64(source_pos),
    )


def composite_control_point_draw_rows(
        transform_controller: TransformController,
        space: Space,
) -> NDArray[np.floating] | None:
    """Return Nx4 control-point rows with fixed columns in composite display space."""
    model = transform_controller.TransformModel
    if model is None or is_rigid_transform(model):
        return None
    if space != Space.Source:
        return None
    rows = _as_numpy_f64(transform_controller.points).copy()
    # Interpolators pass through control points: display position is TargetPoints.
    rows[:, 2:4] = rows[:, 0:2]
    return rows


def composite_uses_display_space(
        transform_controller: TransformController,
        view_type: ViewType | None,
) -> bool:
    """True when composite mesh/grid interactions use target display coordinates."""
    if view_type != ViewType.Composite:
        return False
    model = transform_controller.TransformModel
    return model is not None and not is_rigid_transform(model)


def target_space_lookat_for_stos_view(
        camera: Camera,
        transform_controller: TransformController,
        space: Space,
        view_type: ViewType | None,
) -> NDArray[np.floating]:
    """Return the focused STOS view center in Target (control) space.

    Used by the ``M`` match-view shortcut so Source, Target, and Composite share
    the same on-screen center and magnification.
    """
    lookat = np.asarray(camera.lookat, dtype=np.float64).ravel()[:2]
    if view_type == ViewType.Composite:
        return np.asarray(
            display_lookat_for_composite(camera, transform_controller),
            dtype=np.float64,
        ).ravel()[:2]
    if space == Space.Source:
        if transform_controller.TransformModel is None:
            return lookat
        return _ui_transform_point(transform_controller, True, lookat)
    return lookat


def camera_lookat_from_target_space(
        transform_controller: TransformController | None,
        target_yx: nornir_imageregistration.PointLike,
        space: Space,
) -> NDArray[np.floating]:
    """Map a Target-space point into a panel camera's native lookat space."""
    point = np.asarray(target_yx, dtype=np.float64).ravel()[:2]
    if space != Space.Source:
        return point
    if transform_controller is None or transform_controller.TransformModel is None:
        return point
    return _ui_transform_point(transform_controller, False, point)
