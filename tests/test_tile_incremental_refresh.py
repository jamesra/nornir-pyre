"""Tests for incremental tile refresh during control-point drag."""

import unittest

import numpy as np

from nornir_imageregistration.transforms.meshwithrbffallback import MeshWithRBFFallback
from pyre.controllers.tile_mesh_cache import TileMeshCpuCache, TileMeshCpuEntry
from pyre.space import Space
from pyre.views import gltiles


class TestSimplicesCompatibility(unittest.TestCase):
    """Cached Delaunay topology must not be reused after point-count changes."""

    def test_rejects_stale_high_indices(self) -> None:
        simplices = np.array([[0, 1, 947]], dtype=np.intp)
        self.assertFalse(gltiles._simplices_compatible_with_points(simplices, 85, 948))

    def test_accepts_matching_count_and_indices(self) -> None:
        simplices = np.array([[0, 1, 2], [1, 2, 3]], dtype=np.intp)
        self.assertTrue(gltiles._simplices_compatible_with_points(simplices, 4, 4))


class TestTileCoordsForControlPoints(unittest.TestCase):
    """tile_coords_for_control_points must cover both fixed and warped columns."""

    def test_includes_fixed_and_warped_tile_locations(self) -> None:
        points = np.array(
            [
                [100.0, 100.0, 500.0, 500.0],
                [2000.0, 2000.0, 50.0, 50.0],
                [3000.0, 3000.0, 3000.0, 3000.0],
            ],
            dtype=np.float64,
        )
        transform = MeshWithRBFFallback(points)
        texture_size = (256, 256)
        coords = gltiles.tile_coords_for_control_points(
            4096, 4096, texture_size, np.array([0, 1], dtype=np.intp), transform)

        self.assertIn((0, 0), coords)  # index 0 fixed at (100,100)
        self.assertIn((1, 1), coords)  # index 1 warped at (50,50) -> tile (1,1) with halo


class TestTileMeshCacheInvalidation(unittest.TestCase):
    """Stale CPU mesh entries must be dropped before incremental GL upload."""

    def test_invalidate_tiles_removes_matching_entries(self) -> None:
        cache = TileMeshCpuCache()
        entry = TileMeshCpuEntry(
            vertices=np.zeros((4, 8), dtype=np.float32),
            indices=np.arange(6, dtype=np.uint16),
        )
        cache.put(1, Space.Source, (0, 0), entry)
        cache.put(1, Space.Target, (1, 1), entry)
        gen_before = cache.generation

        cache.invalidate_tiles({(0, 0)})

        self.assertIsNone(cache.get(1, Space.Source, (0, 0)))
        self.assertIsNotNone(cache.get(1, Space.Target, (1, 1)))
        self.assertGreater(cache.generation, gen_before)


class TestTransformModelReplaceClearsMeshCache(unittest.TestCase):
    """Rigid→grid convert must not keep identity quads in the shared CPU cache."""

    def test_replacing_model_clears_tile_mesh_cache(self) -> None:
        from nornir_imageregistration.transforms import CenteredSimilarity2DTransform, ConvertTransform
        from nornir_imageregistration.transforms.transform_type import TransformType
        from pyre.controllers.transformcontroller import TransformController

        rigid = CenteredSimilarity2DTransform(
            target_offset=(10.0, 20.0),
            source_rotation_center=(0.0, 0.0),
            angle=0.1,
            scalar=1.0,
        )
        controller = TransformController(rigid)
        stale = TileMeshCpuEntry(
            vertices=np.zeros((4, 8), dtype=np.float32),
            indices=np.arange(6, dtype=np.uint16),
            is_rigid_quad=True,
        )
        controller.tile_mesh_cache.put(99, Space.Source, (0, 0), stale)
        self.assertIsNotNone(controller.tile_mesh_cache.get(99, Space.Source, (0, 0)))

        grid = ConvertTransform(
            rigid, TransformType.GRID, source_image_shape=(64, 64), grid_dims=(3, 3))
        controller.TransformModel = grid

        self.assertIsNone(controller.tile_mesh_cache.get(99, Space.Source, (0, 0)))
        self.assertFalse(controller.display_strategy.uses_static_tile_quads())


class TestRejectCachedRigidQuadWhenWarpRequired(unittest.TestCase):
    """Composite source must not reuse rigid quads after convert-to-grid."""

    def test_get_or_build_ignores_rigid_quad_when_deformable_required(self) -> None:
        from unittest.mock import MagicMock, patch

        from pyre.views.imagetransformview import ImageTransformView

        view = ImageTransformView.__new__(ImageTransformView)
        view._transform_controller = MagicMock()
        view._transform_controller.display_strategy.uses_static_tile_quads.return_value = False
        view._image_space = Space.Source
        view._warp_into_target_display = True
        view._image_viewmodel = MagicMock()
        view._image_viewmodel.TextureSize = np.array([64, 64], dtype=np.int32)
        cache = TileMeshCpuCache()
        stale = TileMeshCpuEntry(
            vertices=np.zeros((4, 8), dtype=np.float32),
            indices=np.arange(6, dtype=np.uint16),
            is_rigid_quad=True,
        )
        cache.put(1, Space.Source, (0, 0), stale)
        view._transform_controller.tile_mesh_cache = cache
        view._view_model_cache_id = MagicMock(return_value=1)  # type: ignore[method-assign]
        view.get_or_create_tile_globjects = MagicMock(return_value=None)
        mesh_transform = MagicMock()
        rebuilt = TileMeshCpuEntry(
            vertices=np.ones((4, 8), dtype=np.float32),
            indices=np.arange(6, dtype=np.uint16),
            is_rigid_quad=False,
        )
        with patch.object(ImageTransformView, "transform", new_callable=lambda: property(lambda self: mesh_transform)):
            with patch("pyre.views.gltiles.is_rigid_transform", return_value=False):
                with patch("pyre.views.gltiles.build_tile_mesh_cpu", return_value=rebuilt) as build:
                    entry = view._get_or_build_cpu_entry((0, 0))
        build.assert_called_once()
        self.assertFalse(entry.is_rigid_quad)
        self.assertIs(cache.get(1, Space.Source, (0, 0)), rebuilt)


if __name__ == "__main__":
    unittest.main()
