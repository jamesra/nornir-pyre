"""Tests for lazy tile mesh build policy on ImageTransformView."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from pyre.space import Space
from pyre.views.imagetransformview import ImageTransformView


class TestLazyMeshPolicy(unittest.TestCase):
    """Verify rigid transforms keep eager mesh builds; deformable transforms use lazy builds."""

    def _make_view(self) -> ImageTransformView:
        view = ImageTransformView.__new__(ImageTransformView)
        view._transform_controller = MagicMock()
        view._transform_controller.display_strategy.uses_static_tile_quads.return_value = False
        view._image_viewmodel = None
        view._tile_render_data = {}
        view._built_mesh_tiles = set()
        view._lazy_mesh_pending_repaint = False
        view._gl_initialized = True
        view._eager_tile_meshes = False
        # Composite source FBO: only this path builds a deformable CP mesh.
        view._image_space = Space.Source
        view._warp_into_target_display = True
        return view

    def test_lazy_mesh_enabled_for_deformable_transform(self) -> None:
        view = self._make_view()
        mesh_transform = MagicMock()
        with patch.object(ImageTransformView, "transform", new_callable=lambda: property(lambda self: mesh_transform)):
            with patch("pyre.views.gltiles.is_rigid_transform", return_value=False):
                self.assertTrue(view._uses_lazy_mesh_build())

    def test_lazy_mesh_disabled_for_rigid_transform(self) -> None:
        view = self._make_view()
        rigid_transform = MagicMock()
        with patch.object(ImageTransformView, "transform", new_callable=lambda: property(lambda self: rigid_transform)):
            with patch("pyre.views.gltiles.is_rigid_transform", return_value=True):
                self.assertFalse(view._uses_lazy_mesh_build())

    def test_lazy_mesh_disabled_for_composite_source_eager_subview(self) -> None:
        """Composite source FBO uses eager full-grid meshes so magenta always appears."""
        view = self._make_view()
        view._eager_tile_meshes = True
        mesh_transform = MagicMock()
        with patch.object(ImageTransformView, "transform", new_callable=lambda: property(lambda self: mesh_transform)):
            with patch("pyre.views.gltiles.is_rigid_transform", return_value=False):
                self.assertFalse(view._uses_lazy_mesh_build())

    def test_lazy_mesh_disabled_when_eager_flag_set(self) -> None:
        view = self._make_view()
        view._eager_tile_meshes = True
        mesh_transform = MagicMock()
        with patch.object(ImageTransformView, "transform", new_callable=lambda: property(lambda self: mesh_transform)):
            with patch("pyre.views.gltiles.is_rigid_transform", return_value=False):
                self.assertFalse(view._uses_lazy_mesh_build())

    def test_lazy_mesh_disabled_for_target_panel(self) -> None:
        """Target image stays on static quads; CP drag must not rebuild a warp mesh."""
        view = self._make_view()
        view._image_space = Space.Target
        view._warp_into_target_display = False
        mesh_transform = MagicMock()
        with patch.object(ImageTransformView, "transform", new_callable=lambda: property(lambda self: mesh_transform)):
            with patch("pyre.views.gltiles.is_rigid_transform", return_value=False):
                self.assertTrue(view._use_static_tile_quads())
                self.assertFalse(view._uses_lazy_mesh_build())

    def test_lazy_mesh_disabled_for_standalone_source_panel(self) -> None:
        """Standalone Source shows native source image; warp mesh is composite-only."""
        view = self._make_view()
        view._image_space = Space.Source
        view._warp_into_target_display = False
        mesh_transform = MagicMock()
        with patch.object(ImageTransformView, "transform", new_callable=lambda: property(lambda self: mesh_transform)):
            with patch("pyre.views.gltiles.is_rigid_transform", return_value=False):
                self.assertTrue(view._use_static_tile_quads())
                self.assertFalse(view._uses_lazy_mesh_build())

    def test_point_moved_skips_incremental_for_static_quads(self) -> None:
        view = self._make_view()
        view._image_space = Space.Target
        view._warp_into_target_display = False
        mesh_transform = MagicMock()
        with patch.object(ImageTransformView, "transform", new_callable=lambda: property(lambda self: mesh_transform)):
            with patch("pyre.views.gltiles.is_rigid_transform", return_value=False):
                with patch.object(view, "update_tiles_for_point_indices") as update_tiles:
                    view.OnPointMoved(view._transform_controller, MagicMock())
        update_tiles.assert_not_called()

    def test_invalidate_clears_built_tiles(self) -> None:
        view = self._make_view()
        view._tile_render_data[(0, 0)] = MagicMock(mesh_populated=True)
        view._built_mesh_tiles.add((0, 0))
        view._invalidate_tile_meshes()
        self.assertEqual(view._tile_render_data, {})
        self.assertEqual(view._built_mesh_tiles, set())


if __name__ == "__main__":
    unittest.main()
