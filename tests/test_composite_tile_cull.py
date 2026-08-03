"""Tests for composite tile culling policy in ImageTransformView."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import numpy as np

import nornir_imageregistration
from pyre.interfaces.viewtype import ViewType
from pyre.space import Space
from pyre.views.imagetransformview import ImageTransformView


class TestCompositeTileCull(unittest.TestCase):
    """Composite FBO draws must not cull tiles using display-space bounds."""

    def _make_view(self) -> ImageTransformView:
        view = ImageTransformView.__new__(ImageTransformView)
        view._transform_controller = MagicMock()
        view._transform_controller.display_strategy.uses_static_tile_quads.return_value = False
        view._image_viewmodel = MagicMock()
        view._image_viewmodel.height = 512
        view._image_viewmodel.width = 512
        view._image_viewmodel.TextureSize = np.array([128, 128], dtype=np.int32)
        view._image_viewmodel.NumCols = 4
        view._image_viewmodel.NumRows = 4
        view._image_viewmodel.ImageArray = [[1] * 4 for _ in range(4)]
        view._image_viewmodel.generate_grid_indicies.return_value = [
            (ix, iy) for ix in range(4) for iy in range(4)
        ]
        view._image_space = Space.Source
        view._tile_render_data = {}
        view._built_mesh_tiles = set()
        view._lazy_mesh_pending_repaint = False
        view._eager_tile_meshes = False
        view._warp_into_target_display = True
        view._gl_initialized = True
        view.get_or_create_tile_globjects = MagicMock(return_value=MagicMock(mesh_populated=True))
        return view

    def test_composite_draw_uses_no_tile_cull_rect(self) -> None:
        view = self._make_view()
        display_bounds = nornir_imageregistration.Rectangle.CreateFromBounds(
            np.array([100.0, 200.0, 300.0, 400.0], dtype=np.float64))
        captured: dict[str, object] = {}

        def _fake_ensure(visible_coords, *, max_tiles=None) -> None:
            captured["visible_coords"] = visible_coords

        mesh_transform = MagicMock()
        with patch.object(ImageTransformView, "transform", new_callable=lambda: property(lambda self: mesh_transform)):
            with patch("pyre.views.gltiles.is_rigid_transform", return_value=False):
                with patch.object(view, "_ensure_visible_tile_meshes", side_effect=_fake_ensure):
                    with patch("pyre.views.imagetransformview.shaders.texture_shader.draw"):
                        view._draw_imageviewmodel(
                            view_proj=np.eye(4, dtype=np.float32),
                            image_viewmodel=view._image_viewmodel,
                            space=Space.Target,
                            bounding_box=display_bounds,
                            view_type=ViewType.Composite,
                        )
        coords = captured.get("visible_coords")
        self.assertIsInstance(coords, set)
        self.assertEqual(len(coords), 16)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
