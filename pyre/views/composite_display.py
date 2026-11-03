"""Composite target-display camera and mouse helpers.

Composite display invariant
---------------------------
The composite window uses **target display space** for overlay, camera, and hit-testing.

* **Target (control) layer** — drawn in native target coordinates; static reference.
* **Source (mapped) layer** — warped into target space via the forward transform;
  moves/deforms during alignment.
* **Camera ``lookat``** — stored in target display space. Pan/zoom translate that
  lookat directly; the registration ``Transform`` / ``InverseTransform`` are used
  only for image warp and for mouse/command pivots (not for camera navigation).

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


def _as_numpy_f64(values: NDArray[np.floating] | object, *,
                  copy: bool = False) -> NDArray[np.floating]:
    """Convert transform output to host float64 for Camera and Qt paths.

    Pass ``copy=True`` when the caller mutates the result. The conversion alone returns a
    view when *values* is already host float64, so mutating it would reach through into
    live transform storage.
    """
    if hasattr(values, "get"):
        values = values.get()  # type: ignore[union-attr]
    # copy=None is NumPy 2's copy-only-if-needed; copy=False would raise when one is needed.
    return np.array(values, dtype=np.float64, copy=copy or None)


def _finite_yx(values: NDArray[np.floating] | object) -> NDArray[np.floating] | None:
    """Return a length-2 (y, x) vector when finite; otherwise None."""
    arr = _as_numpy_f64(values).ravel()
    if arr.shape[0] < 2 or not np.all(np.isfinite(arr[:2])):
        return None
    return arr[:2].copy()


def _reference_world_extent(
        camera: Camera,
        transform_controller: TransformController | None = None,
) -> float:
    """Typical world scale for rejecting absurd camera / display positions."""
    # Floor covers stub cameras / tiny rigid models so ordinary pan deltas
    # (a few pixels) are not rejected when visible size is unavailable.
    extent = 1000.0
    visible = getattr(camera, "visible_world_size", None)
    if visible is not None:
        try:
            vis = np.asarray(visible, dtype=np.float64).ravel()
            if vis.size > 0 and np.all(np.isfinite(vis)):
                extent = max(extent, float(np.max(np.abs(vis))))
        except Exception:
            pass
    if transform_controller is not None:
        width = getattr(transform_controller, "width", None)
        height = getattr(transform_controller, "height", None)
        if width is not None and height is not None:
            try:
                extent = max(extent, float(width), float(height))
            except Exception:
                pass
        model = getattr(transform_controller, "TransformModel", None)
        if model is not None:
            for attr in ("FixedBoundingBox", "MappedBoundingBox"):
                if not hasattr(model, attr):
                    continue
                try:
                    bb = getattr(model, attr)
                    extent = max(extent, float(bb.Width), float(bb.Height))
                except Exception:
                    pass
    return extent


def is_plausible_world_delta(
        delta: NDArray[np.floating] | object,
        camera: Camera,
        *,
        max_factor: float = 2.0,
        transform_controller: TransformController | None = None,
) -> bool:
    """True when a pan/zoom cursor-lock delta fits in a couple of viewports."""
    arr = _finite_yx(delta)
    if arr is None:
        return False
    limit = _reference_world_extent(camera, transform_controller) * max_factor
    return float(np.max(np.abs(arr))) <= limit


def is_plausible_world_point(
        point: NDArray[np.floating] | object,
        camera: Camera,
        *,
        max_factor: float = 100.0,
        transform_controller: TransformController | None = None,
) -> bool:
    """True when a world point is finite and within a generous image/view bound."""
    arr = _finite_yx(point)
    if arr is None:
        return False
    limit = _reference_world_extent(camera, transform_controller) * max_factor
    return float(np.max(np.abs(arr))) <= limit


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
    """Map one point for mouse/command pivots; always extrapolate so NaNs do not leak."""
    fn = transform_controller.Transform if forward else transform_controller.InverseTransform
    return _transform_single_point(fn, yx, extrapolate=True)


def _fallback_display_lookat(
        camera: Camera,
        transform_controller: TransformController,
        lookat: NDArray[np.floating],
) -> NDArray[np.floating]:
    """Finite display-space center when camera lookat is unusable."""
    if is_plausible_world_point(
            lookat, camera, transform_controller=transform_controller):
        return np.asarray(lookat, dtype=np.float64).ravel()[:2].copy()
    model = transform_controller.TransformModel
    if model is not None and hasattr(model, "FixedBoundingBox"):
        try:
            center = np.asarray(model.FixedBoundingBox.Center, dtype=np.float64).ravel()[:2]
            if _finite_yx(center) is not None:
                return center.copy()
        except Exception:
            pass
    return np.zeros(2, dtype=np.float64)


def display_lookat_for_composite(
        camera: Camera,
        transform_controller: TransformController,
) -> NDArray[np.floating]:
    """Return the composite camera lookat (already target display space)."""
    lookat = np.asarray(camera.lookat, dtype=np.float64).ravel()[:2]
    if is_plausible_world_point(
            lookat, camera, transform_controller=transform_controller):
        return lookat.copy()
    return _fallback_display_lookat(camera, transform_controller, lookat)


def lookat_from_display_position(
        transform_controller: TransformController,
        display_yx: NDArray[np.floating],
) -> NDArray[np.floating]:
    """Return *display_yx* as camera lookat (composite lookat is display-native).

    Kept as a named helper for call sites that historically solved
    ``Transform(lookat) == display``; that solve is no longer required.
    """
    del transform_controller
    display = _as_numpy_f64(display_yx).ravel()[:2]
    return display.copy()


def rebase_composite_camera_after_rigid_gesture(
        camera: Camera,
        transform_controller: TransformController,
) -> None:
    """No-op: composite lookat is already target display space.

    Rigid translate freezes shader uniforms for the target layer; the camera does
    not need rebasing when the gesture ends.
    """
    del camera, transform_controller


def rebase_composite_camera_to_display(
        camera: Camera,
        transform_controller: TransformController,
        display_yx: NDArray[np.floating],
) -> None:
    """Pin composite ``camera.lookat`` to a target-display point (identity assign).

    Used when a remesh/registration path stashed a display center to restore.
    Does not call InverseTransform.
    """
    if not is_plausible_world_point(
            display_yx, camera, transform_controller=transform_controller):
        return
    camera.lookat = np.asarray(display_yx, dtype=np.float64).ravel()[:2]


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
    display_lookat = display_lookat_for_composite(camera, transform_controller)
    view_proj = camera.view_proj_for_lookat(display_lookat, width, height)
    # lookat is display-native, so the camera visible box is already display space.
    display_bounds = visible_rectangle_around_lookat(
        display_lookat, camera.scale, height, width)
    del transform_controller
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
    """Identity for display-native lookat; kept for callers that still pass a model."""
    del model
    return np.asarray(delta_display, dtype=np.float64).ravel()[:2].copy()


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


def apply_composite_display_pan_delta(
        camera: Camera,
        transform_controller: TransformController,
        delta_display: NDArray[np.floating],
) -> None:
    """Pan the composite camera by a target-display delta (plain translate)."""
    delta = np.asarray(delta_display, dtype=np.float64).ravel()[:2]
    if not is_plausible_world_delta(
            delta, camera, transform_controller=transform_controller):
        return
    bounds = transform_controller._cached_composite_display_bounds
    if bounds is not None:
        transform_controller._cached_composite_display_bounds = _translate_display_rectangle(
            bounds, delta)
    camera.translate(delta)


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
    if not is_plausible_world_point(
            display_yx, camera, transform_controller=transform_controller):
        return None
    if transform_controller.freeze_composite_display_during_point_drag():
        source_pos = display_yx
    else:
        source_pos = _ui_transform_point(transform_controller, False, display_yx)
        if not is_plausible_world_point(
                source_pos, camera, transform_controller=transform_controller):
            # Keep status/pan usable when InverseTransform is outside the hull
            # or explodes to astronomical coordinates.
            source_pos = display_yx
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
    # points is a live view into the transform, so the result must not alias it. Converting and
    # copying in one pass replaces `_as_numpy_f64(...).copy()`, which made a second full Nx4 pass
    # whenever the model dtype was not already float64 -- it is float32 today. (#169)
    rows = _as_numpy_f64(transform_controller.points, copy=True)
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
    the same on-screen center and magnification. Composite lookat is already
    target display space.
    """
    lookat = np.asarray(camera.lookat, dtype=np.float64).ravel()[:2]
    if view_type == ViewType.Composite:
        return display_lookat_for_composite(camera, transform_controller)
    if space == Space.Source:
        if transform_controller.TransformModel is None:
            return lookat
        return _ui_transform_point(transform_controller, True, lookat)
    return lookat


def camera_lookat_from_target_space(
        transform_controller: TransformController | None,
        target_yx: nornir_imageregistration.PointLike,
        space: Space,
        view_type: ViewType | None = None,
) -> NDArray[np.floating]:
    """Map a Target-space point into a panel camera's native lookat space.

    Composite cameras store lookat in target display space, so the point is used
    as-is. Source panels InverseTransform; Target panels use the point unchanged.

    When InverseTransform yields a non-finite or runaway source point (folded mesh,
    cold RBF with extrapolate disabled), returns the finite target point unchanged so
    callers do not poison ``camera.lookat``.
    """
    point = np.asarray(target_yx, dtype=np.float64).ravel()[:2]
    if view_type == ViewType.Composite or space != Space.Source:
        return point.copy()
    if transform_controller is None or transform_controller.TransformModel is None:
        return point.copy()
    mapped = _ui_transform_point(transform_controller, False, point)
    finite = _finite_yx(mapped)
    if finite is None:
        return point.copy()
    # Without a camera, bound against transform extents alone.
    extent = 1.0
    model = transform_controller.TransformModel
    for attr in ("MappedBoundingBox", "FixedBoundingBox"):
        if hasattr(model, attr):
            try:
                bb = getattr(model, attr)
                extent = max(extent, float(bb.Width), float(bb.Height))
            except Exception:
                pass
    width = transform_controller.width
    height = transform_controller.height
    if width is not None and height is not None:
        extent = max(extent, float(width), float(height))
    if float(np.max(np.abs(finite))) > extent * 100.0:
        return point.copy()
    return finite
