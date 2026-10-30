"""Tests that gltiles carries one _tile_bounding_rect and no unreachable tile-point helpers.

`gltiles` defined `_tile_bounding_rect` twice. The second definition shadowed the first, so
the earlier one was unreachable, and the helpers that only it and its neighbours called were
dead too -- including `_build_subtile_point_pairs`, which raised `AxisError` on the one line
that gave it a positional `2` where `np.concatenate` expects `axis`.
"""

from __future__ import annotations

import inspect
import re
import unittest

import numpy as np

from pyre.views import gltiles


def _source() -> str:
    return inspect.getsource(gltiles)


class TestTheDuplicateDefinitionIsGone(unittest.TestCase):

    def test_tile_bounding_rect_is_defined_once(self) -> None:
        defs = re.findall(r'^def _tile_bounding_rect\b', _source(), flags=re.MULTILINE)
        self.assertEqual(1, len(defs),
                         'a second def would silently shadow the first')

    def test_the_surviving_definition_is_the_one_the_callers_use(self) -> None:
        params = list(inspect.signature(gltiles._tile_bounding_rect).parameters)
        self.assertEqual(['grid_coords', 'texture_size'], params)

    def test_every_def_in_the_module_is_uniquely_named(self) -> None:
        names = re.findall(r'^def (\w+)', _source(), flags=re.MULTILINE)
        duplicates = sorted({n for n in names if names.count(n) > 1})
        self.assertEqual([], duplicates, f'shadowed module-level defs: {duplicates}')


class TestTheDeadHelpersAreGone(unittest.TestCase):

    def test_the_unreachable_helpers_are_removed(self) -> None:
        for name in ('_build_subtile_point_pairs',
                     '_build_tile_point_pairs',
                     '_tile_bounding_points'):
            with self.subTest(name=name):
                self.assertFalse(hasattr(gltiles, name),
                                 f'{name} had no callers anywhere in the repo')

    def test_no_bogus_positional_axis_remains(self) -> None:
        """np.concatenate's second positional argument is axis, not an array."""
        self.assertNotIn('2).squeeze()', _source())
        for match in re.finditer(r'np\.concatenate\(', _source()):
            tail = _source()[match.end():match.end() + 400]
            self.assertNotRegex(tail.split(')')[0], r'^\s*np\.array\(')

    def test_the_removed_api_was_never_on_the_interface(self) -> None:
        """The deleted helper called GetWarpedPointsInRect through a type: ignore."""
        import nornir_imageregistration
        self.assertFalse(hasattr(nornir_imageregistration.ITransform,
                                 'GetWarpedPointsInRect'))
        self.assertNotIn('GetWarpedPointsInRect', _source())


class TestTheSurvivingHelpersStillWork(unittest.TestCase):
    """The live helpers that shared the removed code are unaffected."""

    def test_the_bounding_rect_maps_grid_coordinates_to_a_rectangle(self) -> None:
        # grid_coords unpacks as (ix, iy), so BottomLeft is (iy * h, ix * w).
        rect = gltiles._tile_bounding_rect(np.array((1, 2)), (256, 256))
        self.assertAlmostEqual(256.0, float(rect.Height))
        self.assertAlmostEqual(256.0, float(rect.Width))
        self.assertAlmostEqual(512.0, float(rect.BottomLeft[0]))
        self.assertAlmostEqual(256.0, float(rect.BottomLeft[1]))

    def test_the_still_used_helpers_are_importable(self) -> None:
        for name in ('_tile_grid_points',
                     '_find_corresponding_points',
                     '_merge_point_pairs_with_transform',
                     '_point_pairs_to_numpy_f64'):
            with self.subTest(name=name):
                self.assertTrue(callable(getattr(gltiles, name)))

    def test_merging_point_pairs_still_removes_duplicates(self) -> None:
        a = np.array([[0.0, 0.0, 1.0, 1.0], [10.0, 10.0, 11.0, 11.0]], dtype=np.float32)
        b = np.array([[10.0, 10.0, 11.0, 11.0], [20.0, 20.0, 21.0, 21.0]], dtype=np.float32)
        merged = gltiles._merge_point_pairs_with_transform(a, b)
        self.assertEqual(3, merged.shape[0])


if __name__ == '__main__':
    unittest.main()
