"""Map source-space camera state to target display space for composite rendering."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

import nornir_imageregistration
from pyre.controllers.transformcontroller import TransformController
from pyre.controllers.transform_display import RigidDisplayStrategy, TransformGesture
from pyre.gl_engine.shaders.texture_shader import TextureShader
from pyre.selection_event_data import PointPair
from pyre.ui.camera import Camera
from pyre.views.gltiles import is_rigid_transform


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


def resolve_composite_display_draw_params(
        camera: Camera,
        transform_controller: TransformController,
        client_size: tuple[int, int],
) -> tuple[NDArray[np.floating], nornir_imageregistration.Rectangle]:
    """Return view_proj and visible bounds in target display space for composite FBO draws."""
    height, width = client_size
    model = transform_controller.TransformModel
    if not is_rigid_transform(model):
        return camera.view_proj, camera.VisibleImageBoundingBox

    view_forward = forward_for_composite_view(transform_controller, model)
    display_lookat = apply_rigid_yx(view_forward, camera.lookat)
    view_proj = camera.view_proj_for_lookat(display_lookat, width, height)
    display_bounds = transform_visible_rectangle(camera.VisibleImageBoundingBox, view_forward)
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


def display_mouse_coords(
        camera: Camera,
        transform_controller: TransformController,
        y: float,
        x: float) -> NDArray[np.floating] | None:
    """Return world (y,x) under the cursor in composite target display space."""
    model = transform_controller.TransformModel
    if model is None or not is_rigid_transform(model):
        return None
    view_forward = forward_for_composite_view(transform_controller, model)
    display_lookat = apply_rigid_yx(view_forward, camera.lookat)
    return camera.image_coords_for_lookat(display_lookat, y, x)


def world_point_pair_for_composite_mouse(
        camera: Camera,
        transform_controller: TransformController,
        y: float,
        x: float,
) -> PointPair | None:
    """Map mouse coords to display-aligned source/target points for composite rigid STOS."""
    display_pos = display_mouse_coords(camera, transform_controller, y, x)
    if display_pos is None:
        return None
    source_pos = np.squeeze(
        transform_controller.InverseTransform(display_pos.reshape(1, 2))
    ).astype(np.float64)
    return PointPair(
        target=np.asarray(display_pos, dtype=np.float64),
        source=np.asarray(source_pos, dtype=np.float64),
    )
