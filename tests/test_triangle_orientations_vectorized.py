"""
_triangle_orientations validated Delaunay orientation one triangle at a time.

It ran a Python loop over every simplex on each cached-simplices rebuild, which is
on the UI thread. The body is a 2D cross product, so it vectorizes exactly.

Measured against the loop it replaced, with results bit-identical throughout:

    points  triangles       loop   vectorized   speedup
        25         40    57.9 us      4.9 us      11.8x
       400        781  1118.9 us     21.8 us      51.4x
      6400      12778 17792.4 us    282.5 us      63.0x

At 6400 points the loop alone took 17.8 ms, longer than a 16.7 ms frame at 60 fps.

The arithmetic stays in the input dtype and widens to float64 only at the end,
which is what the loop did: it accumulated whatever dtype the subtraction produced
and let ``np.asarray(..., dtype=np.float64)`` widen at the end. Computing in float64
throughout would be more robust near degenerate triangles, but it would also change
which topologies ``_topology_still_valid`` accepts, so it is deliberately not done
here.
"""

from __future__ import annotations

import numpy as np
import pytest

from pyre.views.gltiles import _topology_still_valid, _triangle_orientations


def _loop_reference(texture_points, simplices):
    """The implementation this replaced."""
    areas = []
    for tri in simplices:
        p = texture_points[tri]
        areas.append((p[1, 0] - p[0, 0]) * (p[2, 1] - p[0, 1])
                     - (p[2, 0] - p[0, 0]) * (p[1, 1] - p[0, 1]))
    return np.asarray(areas, dtype=np.float64)


def _delaunay(n_points, seed=0, dtype=np.float32):
    from scipy.spatial import Delaunay

    rng = np.random.default_rng(seed)
    pts = (rng.random((n_points, 2)) * 1000.0).astype(dtype)
    return pts, Delaunay(pts).simplices.astype(np.int32)


# --- must match the loop exactly ----------------------------------------------

@pytest.mark.parametrize('n_points', [4, 25, 100, 400])
def test_matches_the_per_triangle_loop_bit_for_bit(n_points):
    pts, simp = _delaunay(n_points)

    assert np.array_equal(_triangle_orientations(pts, simp),
                          _loop_reference(pts, simp))


@pytest.mark.parametrize('dtype', [np.float32, np.float64])
def test_matches_for_either_input_precision(dtype):
    pts, simp = _delaunay(150, dtype=dtype)

    assert np.array_equal(_triangle_orientations(pts, simp),
                          _loop_reference(pts, simp))


def test_the_result_is_widened_to_float64():
    pts, simp = _delaunay(50)

    assert _triangle_orientations(pts, simp).dtype == np.float64


# --- the geometry it encodes --------------------------------------------------

def test_orientation_sign_follows_winding():
    pts = np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]], dtype=np.float32)

    ccw = _triangle_orientations(pts, np.array([[0, 1, 2]], dtype=np.int32))
    cw = _triangle_orientations(pts, np.array([[0, 2, 1]], dtype=np.int32))

    assert ccw[0] == -cw[0]
    assert ccw[0] != 0.0


def test_a_degenerate_triangle_has_zero_area():
    collinear = np.array([[0.0, 0.0], [1.0, 1.0], [2.0, 2.0]], dtype=np.float32)

    areas = _triangle_orientations(collinear, np.array([[0, 1, 2]], dtype=np.int32))

    assert areas[0] == 0.0


def test_the_magnitude_is_twice_the_area():
    pts = np.array([[0.0, 0.0], [4.0, 0.0], [0.0, 3.0]], dtype=np.float32)

    areas = _triangle_orientations(pts, np.array([[0, 1, 2]], dtype=np.int32))

    assert abs(areas[0]) == pytest.approx(2 * 6.0)


# --- shape handling -----------------------------------------------------------

def test_a_single_triangle_returns_one_value():
    pts, simp = _delaunay(4)

    assert _triangle_orientations(pts, simp).shape == (len(simp),)


def test_an_empty_simplex_set_returns_an_empty_array():
    pts = np.zeros((3, 2), dtype=np.float32)
    empty = np.zeros((0, 3), dtype=np.int32)

    assert _triangle_orientations(pts, empty).shape == (0,)


# --- the defect itself: per-triangle Python work ------------------------------

class _CountingPoints(np.ndarray):
    """Counts Python-level indexing, which the loop did once per triangle."""

    def __new__(cls, source):
        obj = np.asarray(source).view(cls)
        obj.gets = 0
        return obj

    def __array_finalize__(self, obj):
        if obj is not None:
            self.gets = getattr(obj, 'gets', 0)

    def __getitem__(self, key):
        self.gets += 1
        return super().__getitem__(key)


def _index_operations(n_points):
    pts, simp = _delaunay(n_points)
    counting = _CountingPoints(pts)
    _triangle_orientations(counting, simp)
    return counting.gets, len(simp)


def test_indexing_does_not_happen_once_per_triangle():
    gets, n_triangles = _index_operations(400)

    assert gets < n_triangles, (
        f'{gets} indexing operations for {n_triangles} triangles: '
        'the orientation check is still looping in Python')


def test_indexing_cost_does_not_grow_with_triangle_count():
    """The property that matters: work per rebuild is independent of mesh size."""
    small_gets, small_n = _index_operations(100)
    large_gets, large_n = _index_operations(1600)

    assert large_n > small_n * 5, 'expected the meshes to differ substantially'
    assert large_gets == small_gets


# --- the caller must be unaffected --------------------------------------------

@pytest.mark.parametrize('n_points', [25, 200])
def test_topology_validation_still_accepts_a_real_delaunay(n_points):
    pts, simp = _delaunay(n_points)

    assert _topology_still_valid(pts, simp) is True


def test_topology_validation_still_rejects_mixed_winding():
    pts, simp = _delaunay(60)
    flipped = simp.copy()
    flipped[0] = flipped[0][::-1]

    assert _topology_still_valid(pts, flipped) is False
