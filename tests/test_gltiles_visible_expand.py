"""Tests for viewport tile coordinate helpers."""

from __future__ import annotations

import unittest

import numpy as np

import nornir_imageregistration
from pyre.views import gltiles


class TestGltilesVisibleExpand(unittest.TestCase):
    """Verify visible tile expansion for lazy mesh prefetch."""

    def test_expand_visible_rectangle_by_tiles(self) -> None:
        rect = nornir_imageregistration.Rectangle.CreateFromBounds(
            np.array((100.0, 200.0, 300.0, 400.0)))
        expanded = gltiles.expand_visible_rectangle_by_tiles(rect, (64, 64), margin_tiles=1)
        y0, x0 = expanded.BottomLeft
        self.assertEqual(y0, 100.0 - 64.0)
        self.assertEqual(x0, 200.0 - 64.0)
        self.assertEqual(y0 + expanded.Height, 300.0 + 64.0)
        self.assertEqual(x0 + expanded.Width, 400.0 + 64.0)

    def test_tile_coords_for_visible_bounds_subset(self) -> None:
        rect = nornir_imageregistration.Rectangle.CreateFromBounds(
            np.array((0.0, 0.0, 64.0, 64.0)))
        coords = gltiles.tile_coords_for_visible_bounds(512, 512, (128, 128), rect)
        self.assertEqual(coords, {(0, 0)})


if __name__ == "__main__":
    unittest.main()
