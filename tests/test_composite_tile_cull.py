"""Tests for composite tile culling policy in ImageTransformView."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import numpy as np

import nornir_imageregistration
from pyre.interfaces.viewtype import ViewType
from pyre.space import Space
from pyre.views.imagetransformview import ImageTransformView
from pyre.views.compositetransformview import composite_layer_ready_to_cache


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

    def _draw_imageviewmodel(self, view: ImageTransformView, **kwargs) -> None:
        mesh_transform = MagicMock()
        contrast = MagicMock(min=0.0, max=255.0, gamma=1.0)
        with patch.object(ImageTransformView, "transform", new_callable=lambda: property(lambda self: mesh_transform)):
            with patch("pyre.views.gltiles.is_rigid_transform", return_value=False):
                with patch("pyre.views.imagetransformview.shaders.texture_shader.draw"):
                    with patch("pyre.image_contrast.contrast_for_space", return_value=contrast):
                        view._draw_imageviewmodel(
                            view_proj=np.eye(4, dtype=np.float32),
                            image_viewmodel=view._image_viewmodel,
                            **kwargs,
                        )

    def test_composite_draw_uses_no_tile_cull_rect(self) -> None:
        view = self._make_view()
        display_bounds = nornir_imageregistration.Rectangle.CreateFromBounds(
            np.array([100.0, 200.0, 300.0, 400.0], dtype=np.float64))
        captured: dict[str, object] = {}

        def _fake_ensure(visible_coords, *, max_tiles=None) -> None:
            captured["visible_coords"] = visible_coords

        with patch.object(view, "_ensure_visible_tile_meshes", side_effect=_fake_ensure):
            self._draw_imageviewmodel(
                view,
                space=Space.Target,
                bounding_box=display_bounds,
                view_type=ViewType.Composite,
            )
        coords = captured.get("visible_coords")
        self.assertIsInstance(coords, set)
        self.assertEqual(len(coords), 16)  # type: ignore[arg-type]

    def test_nan_bounding_box_does_not_raise(self) -> None:
        view = self._make_view()
        nan_bounds = nornir_imageregistration.Rectangle.CreateFromBounds(
            np.array([np.nan, np.nan, np.nan, np.nan], dtype=np.float64))
        captured: dict[str, object] = {}

        def _fake_ensure(visible_coords, *, max_tiles=None) -> None:
            captured["visible_coords"] = visible_coords

        with patch.object(view, "_ensure_visible_tile_meshes", side_effect=_fake_ensure):
            self._draw_imageviewmodel(
                view,
                space=Space.Source,
                bounding_box=nan_bounds,
                view_type=ViewType.Source,
            )
        coords = captured.get("visible_coords")
        self.assertIsInstance(coords, set)
        self.assertEqual(len(coords), 16)  # type: ignore[arg-type]


class TestContrastLookupOutsideTileLoop(unittest.TestCase):
    """#207: contrast_for_space must not run once per tile per frame."""

    def test_contrast_for_space_called_once_per_draw(self) -> None:
        cull = TestCompositeTileCull()
        view = cull._make_view()
        contrast = MagicMock(min=0.0, max=255.0, gamma=1.0)
        mesh_transform = MagicMock()
        with patch.object(
                ImageTransformView, "transform",
                new_callable=lambda: property(lambda self: mesh_transform)):
            with patch("pyre.views.gltiles.is_rigid_transform", return_value=False):
                with patch("pyre.views.imagetransformview.shaders.texture_shader.draw"):
                    with patch(
                            "pyre.image_contrast.contrast_for_space",
                            return_value=contrast) as contrast_lookup:
                        with patch.object(view, "_ensure_visible_tile_meshes"):
                            view._draw_imageviewmodel(
                                view_proj=np.eye(4, dtype=np.float32),
                                image_viewmodel=view._image_viewmodel,
                                space=Space.Source,
                                bounding_box=None,
                                view_type=ViewType.Source,
                            )
        contrast_lookup.assert_called_once_with(Space.Source)

    def test_draw_method_has_no_nested_image_contrast_import(self) -> None:
        import inspect
        source = inspect.getsource(ImageTransformView._draw_imageviewmodel)
        self.assertNotIn(
            'from pyre.image_contrast import',
            source,
            msg='nested import inside the per-tile draw loop (#207)')


class TestEagerMeshSkipDuringInteractive(unittest.TestCase):
    """Composite source must not remesh the full tile grid mid-drag."""

    def test_eager_draw_skips_full_remesh_during_interactive(self) -> None:
        view = ImageTransformView.__new__(ImageTransformView)
        view._transform_controller = MagicMock()
        draw_state = MagicMock()
        draw_state.use_rigid_path = False
        draw_state.source_to_target = None
        draw_state.target_to_source = None
        draw_state.rigid_native_is_target = False
        draw_state.rigid_source_in_target_display = False
        draw_state.rigid_overlay = None
        view._transform_controller.resolve_draw_state.return_value = draw_state
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
        view._eager_tile_meshes = True
        view._warp_into_target_display = True
        view._gl_initialized = True
        view.get_or_create_tile_globjects = MagicMock(return_value=MagicMock(mesh_populated=True))
        mesh_transform = MagicMock()
        contrast = MagicMock(min=0.0, max=255.0, gamma=1.0)
        with patch.object(ImageTransformView, "transform", new_callable=lambda: property(lambda self: mesh_transform)):
            with patch("pyre.views.gltiles.is_rigid_transform", return_value=False):
                with patch("pyre.views.imagetransformview.shaders.texture_shader.draw"):
                    with patch("pyre.image_contrast.contrast_for_space", return_value=contrast):
                        with patch.object(view, "update_all_tile_buffers") as remesh:
                            view._draw_imageviewmodel(
                                view_proj=np.eye(4, dtype=np.float32),
                                image_viewmodel=view._image_viewmodel,
                                space=Space.Source,
                                bounding_box=None,
                                view_type=ViewType.Composite,
                            )
        remesh.assert_not_called()


class TestCompositeLayerFboCache(unittest.TestCase):
    """Empty first-paint FBO fills must not be cached as a complete overlay."""

    def test_uninitialized_view_is_not_ready_to_cache(self) -> None:
        view = MagicMock()
        view._gl_initialized = False
        view.image_view_model = MagicMock()
        view.image_view_model._ImageArray = [[1]]
        self.assertFalse(composite_layer_ready_to_cache(view))

    def test_initialized_view_with_textures_is_ready_to_cache(self) -> None:
        view = MagicMock()
        view._gl_initialized = True
        view.image_view_model = MagicMock()
        view.image_view_model._ImageArray = [[1]]
        self.assertTrue(composite_layer_ready_to_cache(view))

    def test_initialized_view_without_textures_is_not_ready_to_cache(self) -> None:
        view = MagicMock()
        view._gl_initialized = True
        view.image_view_model = MagicMock()
        view.image_view_model._ImageArray = []
        self.assertFalse(composite_layer_ready_to_cache(view))


if __name__ == "__main__":
    unittest.main()
