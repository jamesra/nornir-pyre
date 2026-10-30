"""Tests the stale-cached-topology path in gltiles after the edge-flip repair was removed.

The repair was a pure loss: it rebuilt the whole edge->triangle map after every flip, wrote
flipped triangles with disagreeing windings so the orientation check rejected any odd number
of flips, and was several times slower than scipy.spatial.Delaunay even once corrected.
These tests pin its removal and confirm retriangulation covers the cases it was there for.
"""

from __future__ import annotations

import inspect
import unittest

import numpy as np
import scipy.spatial

from pyre.views import gltiles


class TestTheRepairIsGone(unittest.TestCase):

    def test_the_repair_and_its_private_helpers_are_removed(self) -> None:
        for name in ('_repair_delaunay_by_edge_flips', '_point_in_circumcircle',
                     '_edge_key'):
            with self.subTest(symbol=name):
                self.assertFalse(hasattr(gltiles, name),
                                 f'{name} was only used by the removed repair')

    def test_the_flip_cap_is_gone(self) -> None:
        source = inspect.getsource(gltiles)
        self.assertNotIn('max_flips', source)

    def test_the_helpers_it_shared_are_kept(self) -> None:
        """_triangle_orientations and _topology_still_valid have other callers."""
        for name in ('_triangle_orientations', '_topology_still_valid',
                     '_simplices_index_in_bounds'):
            with self.subTest(symbol=name):
                self.assertTrue(hasattr(gltiles, name))

    def test_the_stale_topology_branch_retriangulates(self) -> None:
        source = inspect.getsource(gltiles.build_tile_mesh_cpu)
        except_at = source.index('except ValueError:')
        delaunay_at = source.index('scipy.spatial.Delaunay')
        self.assertLess(except_at, delaunay_at,
                        'the invalid-cache branch must fall through to retriangulation')


class TestTheWindingDefectItHad(unittest.TestCase):
    """Documents why the repair could not succeed, so it is not reintroduced."""

    @staticmethod
    def _orientation(points: np.ndarray, tri: tuple[int, int, int]) -> float:
        a, b, c = (points[i] for i in tri)
        return float((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))

    def test_the_old_flip_ordering_disagrees_on_winding(self) -> None:
        """[k,l,i] and [k,l,j] have opposite orientations for a convex quad."""
        # A unit square: edge (i,j) is the diagonal, k and l the opposite corners.
        points = np.array([[0.0, 0.0], [1.0, 1.0], [1.0, 0.0], [0.0, 1.0]])
        i, j, k, l = 0, 1, 2, 3

        old0 = self._orientation(points, (k, l, i))
        old1 = self._orientation(points, (k, l, j))
        self.assertNotEqual(np.sign(old0), np.sign(old1),
                            'this disagreement is what failed the orientation check')

        new0 = self._orientation(points, (i, k, l))
        new1 = self._orientation(points, (j, l, k))
        self.assertEqual(np.sign(new0), np.sign(new1),
                         'a correctly wound flip keeps one orientation')

    def test_the_orientation_check_rejects_mixed_winding(self) -> None:
        points = np.array([[0.0, 0.0], [1.0, 1.0], [1.0, 0.0], [0.0, 1.0]])
        mixed = np.array([[2, 3, 0], [2, 3, 1]], dtype=np.intp)
        self.assertFalse(gltiles._topology_still_valid(points, mixed))

        consistent = np.array([[0, 2, 3], [1, 3, 2]], dtype=np.intp)
        self.assertTrue(gltiles._topology_still_valid(points, consistent))


class TestRetriangulationCoversTheCases(unittest.TestCase):
    """Delaunay must succeed on the inputs the repair was reached for."""

    @staticmethod
    def _drag_case(n_points: int, seed: int, drag: float):
        rng = np.random.default_rng(seed)
        points = rng.uniform(0.0, 1.0, size=(n_points, 2))
        simplices = scipy.spatial.Delaunay(points).simplices.copy()
        idx = int(np.argmin(np.linalg.norm(points - np.array([0.5, 0.5]), axis=1)))
        moved = points.copy()
        direction = rng.normal(size=2)
        moved[idx] = points[idx] + direction / np.linalg.norm(direction) * drag
        return moved, simplices

    def test_retriangulation_is_valid_where_the_cache_was_not(self) -> None:
        stale_seen = False
        for seed in range(20):
            moved, simplices = self._drag_case(120, seed=seed, drag=0.08)
            if not gltiles._topology_still_valid(moved, simplices):
                stale_seen = True
            fresh = scipy.spatial.Delaunay(moved).simplices.copy()
            self.assertTrue(gltiles._topology_still_valid(moved, fresh),
                            f'retriangulation invalid for seed {seed}')
        self.assertTrue(stale_seen,
                        'the fixture should produce at least one stale cache')

    def test_retriangulation_indexes_every_point_in_range(self) -> None:
        moved, _ = self._drag_case(200, seed=3, drag=0.05)
        fresh = scipy.spatial.Delaunay(moved).simplices.copy()
        self.assertTrue(gltiles._simplices_index_in_bounds(fresh, moved.shape[0]))
        self.assertLess(int(fresh.max()), moved.shape[0])
        self.assertGreaterEqual(int(fresh.min()), 0)

    def test_indices_still_fit_the_uint16_buffer(self) -> None:
        """The caller casts simplices to uint16 for the index buffer."""
        moved, _ = self._drag_case(400, seed=11, drag=0.05)
        fresh = scipy.spatial.Delaunay(moved).simplices.copy()
        self.assertLess(int(fresh.max()), np.iinfo(np.uint16).max)


if __name__ == '__main__':
    unittest.main()
