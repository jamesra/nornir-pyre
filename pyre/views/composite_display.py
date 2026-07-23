"""Map source-space camera state to target display space for composite rendering.

Composite view product default
------------------------------
The composite window is for aligning the **warped (green)** section to the fixed
(purple) reference. User edits should move or deform the warped layer on screen,
not drag the fixed layer opposite the control points.

For mesh, grid, and RBF transforms, control-point drags on composite use
``Space.Source`` command space (fixed anchors / ``TargetPoints``) but glyphs,
hit-testing, and mouse deltas are resolved in **target display space** so the
green image follows the cursor. Fixed CP positions are drawn at
``Transform(fixed_point)`` in that space.

Rigid whole-layer translate/rotate on composite is a deliberate exception: the
purple layer moves during the gesture while green stays frozen
(``RigidDisplayStrategy``); registration still updates the shared transform.
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
    corners = np.asarray(rect.Corners, dtype=np.float64)
    mapped = _as_numpy_f64(transform_controller.Transform(corners))
    return nornir_imageregistration.Rectangle.CreateFromBounds(
        np.array([
            float(np.min(mapped[:, 0])),
            float(np.min(mapped[:, 1])),
            float(np.max(mapped[:, 0])),
            float(np.max(mapped[:, 1])),
        ]))


def forward_for_composite_view(
        transform_controller: TransformController,
        model: object,
) -> NDArray[np.floating]:
    """Forward matrix used to couple camera lookat to composite view_proj.

    During whole-layer translate gestures the view_proj must not track live
    registration translation (green is frozen); only shader uniforms update.
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
        fn: Callable[[NDArray[np.floating]], NDArray[np.floating] | object],
        yx: NDArray[np.floating] | object) -> NDArray[np.floating]:
    """Apply a transform that accepts Nx2 points and return a (y, x) vector."""
    arr = _as_numpy_f64(yx).reshape(1, 2)
    return np.squeeze(_as_numpy_f64(fn(arr)))


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
    lookat = np.asarray(camera.lookat, dtype=np.float64)
    return _transform_single_point(transform_controller.Transform, lookat)


def lookat_from_display_position(
        transform_controller: TransformController,
        display_yx: NDArray[np.floating],
) -> NDArray[np.floating]:
    """Map a composite display-space (y,x) position back to source-camera lookat."""
    return _transform_single_point(transform_controller.InverseTransform, display_yx)


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
    source_pos = _transform_single_point(transform_controller.InverseTransform, display_pos)
    return PointPair(
        target=_as_numpy_f64(display_pos),
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
    fixed_yx = rows[:, 0:2]
    rows[:, 0:2] = _as_numpy_f64(transform_controller.Transform(fixed_yx))
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
