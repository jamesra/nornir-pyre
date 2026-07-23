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


if __name__ == "__main__":
    unittest.main()
