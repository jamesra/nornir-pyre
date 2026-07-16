"""Map source-space camera state to target display space for composite rendering."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

import nornir_imageregistration
from pyre.controllers.transformcontroller import TransformController
from pyre.gl_engine.shaders.texture_shader import TextureShader
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

    forward, _ = TextureShader.rigid_matrices_from_transform(model)
    display_lookat = apply_rigid_yx(forward, camera.lookat)
    view_proj = camera.view_proj_for_lookat(display_lookat, width, height)
    display_bounds = transform_visible_rectangle(camera.VisibleImageBoundingBox, forward)
    return view_proj, display_bounds
