"""Pyre xp + last-moment host conversion for Qt/GL/SciPy consumers."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import numpy as np
from hypothesis import example, given, settings
from hypothesis import strategies as st

import nornir_imageregistration
from nornir_imageregistration.computational_lib import HasCupy
from nornir_imageregistration.transforms.meshwithrbffallback import MeshWithRBFFallback

from pyre.array_host import yx_host, leading_axis_len
from pyre.commands.stos.point_coords import known_yx_from_pair
from pyre.common import _indices_to_remove_for_mask
from pyre.selection_event_data import PointPair
from pyre.space import Space
from pyre.views.gltiles import (
    _find_corresponding_points,
    _merge_point_pairs_with_transform,
    _point_pairs_to_numpy_f64,
    collect_verticies_within_bounding_box,
)
from pyre.views.imagetransformview import ImageTransformView, mesh_overlay_verts_xy


def _identity_mesh_square() -> MeshWithRBFFallback:
    points = np.array(
        [
            [0.0, 0.0, 0.0, 0.0],
            [0.0, 32.0, 0.0, 32.0],
            [32.0, 0.0, 32.0, 0.0],
            [32.0, 32.0, 32.0, 32.0],
        ],
        dtype=np.float64,
    )
    return MeshWithRBFFallback(points)


class TestYxHost(unittest.TestCase):
    @given(
        y=st.floats(-1e6, 1e6, allow_nan=False, allow_infinity=False),
        x=st.floats(-1e6, 1e6, allow_nan=False, allow_infinity=False),
    )
    @example(y=3.0, x=4.0)
    @settings(max_examples=25, deadline=None)
    def test_yx_host_numpy_row_and_matrix(self, y: float, x: float) -> None:
        expected = np.array([y, x], dtype=np.float64)
        np.testing.assert_allclose(yx_host(np.array([y, x], dtype=np.float64)), expected)
        np.testing.assert_allclose(yx_host(np.array([[y, x]], dtype=np.float64)), expected)
        self.assertIsInstance(yx_host(expected), np.ndarray)

    @unittest.skipUnless(HasCupy(), "requires CuPy")
    def test_yx_host_from_cupy_row(self) -> None:
        import cupy as cp

        mapped = cp.asarray([[5.0, 6.0]], dtype=cp.float64)
        host = yx_host(mapped)
        np.testing.assert_allclose(host, [5.0, 6.0])
        self.assertIsInstance(host, np.ndarray)
        self.assertFalse(isinstance(host, cp.ndarray))

    @unittest.skipUnless(HasCupy(), "requires CuPy")
    def test_known_yx_from_pair_accepts_cupy(self) -> None:
        import cupy as cp

        point = PointPair(
            target=cp.asarray([10.0, 20.0], dtype=cp.float64),
            source=cp.asarray([3.0, 4.0], dtype=cp.float64),
        )
        np.testing.assert_allclose(known_yx_from_pair(point, Space.Target), [10.0, 20.0])
        np.testing.assert_allclose(known_yx_from_pair(point, Space.Source), [3.0, 4.0])


class TestMeshOverlayAndMerge(unittest.TestCase):
    def test_mesh_overlay_verts_xy_numpy(self) -> None:
        pts = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float64)
        verts = mesh_overlay_verts_xy(pts)
        np.testing.assert_allclose(verts, [[2.0, 1.0], [4.0, 3.0]])
        self.assertIsInstance(verts, np.ndarray)

    @unittest.skipUnless(HasCupy(), "requires CuPy")
    def test_mesh_overlay_verts_xy_from_cupy(self) -> None:
        import cupy as cp

        pts = cp.asarray([[1.0, 2.0], [3.0, 4.0]], dtype=cp.float64)
        verts = mesh_overlay_verts_xy(pts)
        np.testing.assert_allclose(verts, [[2.0, 1.0], [4.0, 3.0]])
        self.assertIsInstance(verts, np.ndarray)
        self.assertFalse(isinstance(verts, cp.ndarray))

    @unittest.skipUnless(HasCupy(), "requires CuPy")
    def test_draw_lines_accepts_cupy_source_points(self) -> None:
        import cupy as cp

        mesh = _identity_mesh_square()
        mesh.InitializeDataStructures()
        cupy_src = cp.asarray(
            nornir_imageregistration.EnsureNumpyArray(mesh.SourcePoints))
        view = ImageTransformView.__new__(ImageTransformView)
        controller = MagicMock()
        controller.TransformModel = mesh
        view._transform_controller = controller
        with patch.object(type(mesh), "SourcePoints", new=property(lambda self: cupy_src)):
            with patch("pyre.views.DrawTriangles") as draw:
                view.draw_lines(draw_in_fixed_space=False)
        draw.assert_called_once()
        verts = draw.call_args.args[0]
        self.assertIsInstance(verts, np.ndarray)
        self.assertFalse(isinstance(verts, cp.ndarray))

    def test_merge_point_pairs_numpy(self) -> None:
        a = np.array([[0.0, 0.0, 1.0, 1.0]], dtype=np.float64)
        b = np.array([[2.0, 2.0, 3.0, 3.0]], dtype=np.float64)
        merged = _merge_point_pairs_with_transform(a, b)
        host = nornir_imageregistration.EnsureNumpyArray(merged)
        self.assertEqual(host.shape[0], 2)

    @unittest.skipUnless(HasCupy(), "requires CuPy")
    def test_merge_point_pairs_numpy_and_cupy(self) -> None:
        import cupy as cp

        a = np.array([[0.0, 0.0, 1.0, 1.0]], dtype=np.float64)
        b = cp.asarray([[2.0, 2.0, 3.0, 3.0]], dtype=cp.float64)
        merged = _merge_point_pairs_with_transform(a, b)
        host = nornir_imageregistration.EnsureNumpyArray(merged)
        self.assertEqual(int(host.shape[0]), 2)
        rows = {tuple(np.round(row, 6)) for row in host}
        self.assertIn((0.0, 0.0, 1.0, 1.0), rows)
        self.assertIn((2.0, 2.0, 3.0, 3.0), rows)

    @unittest.skipUnless(HasCupy(), "requires CuPy")
    def test_find_corresponding_points_stays_on_transform_backend(self) -> None:
        import cupy as cupy_mod

        class _CupyOffsetTransform:
            def Transform(self, points, extrapolate: bool = True):
                return cupy_mod.asarray(points, dtype=cupy_mod.float32) + 1.0

            def InverseTransform(self, points, extrapolate: bool = True):
                return cupy_mod.asarray(points, dtype=cupy_mod.float32) - 1.0

        query = np.array([[0.0, 0.0], [2.0, 4.0]], dtype=np.float32)
        pairs = _find_corresponding_points(_CupyOffsetTransform(), query, forward_transform=True)
        self.assertTrue(isinstance(pairs, cupy_mod.ndarray))
        host = nornir_imageregistration.EnsureNumpyArray(pairs)
        np.testing.assert_allclose(host[:, 0:2], query + 1.0)
        np.testing.assert_allclose(host[:, 2:4], query)

        merged = _merge_point_pairs_with_transform(
            pairs, cupy_mod.asarray([[10.0, 10.0, 0.0, 0.0]], dtype=cupy_mod.float32))
        self.assertTrue(isinstance(merged, cupy_mod.ndarray))
        host_pairs = _point_pairs_to_numpy_f64(merged)
        self.assertIsInstance(host_pairs, np.ndarray)
        self.assertFalse(isinstance(host_pairs, cupy_mod.ndarray))
        self.assertEqual(int(host_pairs.shape[0]), 3)

    @unittest.skipUnless(HasCupy(), "requires CuPy")
    def test_collect_verticies_host_verts_after_cupy_transform_points(self) -> None:
        import cupy as cupy_mod

        mesh = _identity_mesh_square()
        mesh.InitializeDataStructures()
        rect = nornir_imageregistration.Rectangle.CreateFromBounds(np.array((0.0, 0.0, 32.0, 32.0)))
        cupy_pairs = cupy_mod.asarray(
            nornir_imageregistration.EnsureNumpyArray(mesh.points), dtype=cupy_mod.float32)
        with patch.object(type(mesh), "GetPointPairsInSourceRect", return_value=cupy_pairs):
            verts = collect_verticies_within_bounding_box(rect, mesh, Space.Source)
        host = _point_pairs_to_numpy_f64(verts)
        self.assertIsInstance(host, np.ndarray)
        self.assertGreaterEqual(int(host.shape[0]), 4)
        self.assertEqual(int(host.shape[1]), 4)

    @unittest.skipUnless(HasCupy(), "requires CuPy")
    def test_indices_to_remove_accepts_cupy_points(self) -> None:
        import cupy as cp

        mask = np.ones((8, 8), dtype=np.uint8)
        mask[0, 0] = 0
        points = cp.asarray([[0.2, 0.2], [3.0, 3.0]], dtype=cp.float64)
        idx = _indices_to_remove_for_mask(points, mask)
        np.testing.assert_array_equal(idx, np.array([0], dtype=np.int32))


class TestLeadingAxisLen(unittest.TestCase):
    def test_none_is_zero(self) -> None:
        self.assertEqual(leading_axis_len(None), 0)

    def test_numpy_rows(self) -> None:
        pts = np.zeros((7, 4), dtype=np.float64)
        self.assertEqual(leading_axis_len(pts), 7)

    @given(n=st.integers(min_value=0, max_value=64), w=st.integers(min_value=1, max_value=8))
    @example(n=0, w=4)
    @example(n=4, w=4)
    @settings(max_examples=25, deadline=None)
    def test_matches_shape0(self, n: int, w: int) -> None:
        pts = np.zeros((n, w), dtype=np.float64)
        self.assertEqual(leading_axis_len(pts), n)

    @unittest.skipUnless(HasCupy(), "requires CuPy")
    def test_cupy_does_not_require_implicit_numpy(self) -> None:
        import cupy as cp

        pts = cp.zeros((5, 4), dtype=cp.float64)
        self.assertEqual(leading_axis_len(pts), 5)


if __name__ == "__main__":
    unittest.main()
