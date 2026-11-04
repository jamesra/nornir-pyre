"""Pyre maps mesh points outside the control-point hull with the nearest hull triangle's affine.

Before, outside the hull Pyre either built the mesh's RBF fallback (a weight solve on the UI
thread) or, during a drag and before the RBF prewarm finished, got NaN, so tiles and cursor
mapping stopped at the hull. Image warping already used hull affine (nornir-imageregistration
598645c); Pyre's display and cursor mapping now match it. Grids keep their RBF fallback.
"""
from __future__ import annotations

import threading
import unittest

import nornir_imageregistration
import numpy as np
from nornir_imageregistration.computational_lib import HasCupy
from nornir_imageregistration.transforms import one_way_rbftransform as owr
from pyre import mesh_hull_affine
from pyre.controllers.transformcontroller import TransformController
from pyre.views import gltiles

_AFFINE = np.array([[1.02, 0.03], [-0.04, 0.97]])
_OFFSET = np.array([12.0, -7.0])
_FAR_SOURCE = np.array([[-300.0, -200.0], [900.0, 40.0], [50.0, 1200.0]])
_INSIDE_SOURCE = np.array([[250.0, 300.0], [400.0, 200.0]])


def _mesh_points() -> np.ndarray:
    """Control points from one global affine: target = source @ A + b."""
    source = np.random.default_rng(3).uniform(100, 500, (40, 2))
    return np.hstack((source @ _AFFINE + _OFFSET, source))


class _CountRBFSolves:
    """Counts RBF weight solves on the calling (UI) thread; the controller's prewarm worker is not counted."""

    def __enter__(self):
        self.count = 0
        self._real = owr.OneWayRBFWithLinearCorrection.CalculateRBFWeights
        caller = threading.get_ident()

        def counting(*args, **kwargs):
            if threading.get_ident() == caller:
                self.count += 1
            return self._real(*args, **kwargs)

        owr.OneWayRBFWithLinearCorrection.CalculateRBFWeights = staticmethod(counting)
        return self

    def __exit__(self, *exc):
        owr.OneWayRBFWithLinearCorrection.CalculateRBFWeights = staticmethod(self._real)


class _MeshCases:

    def _model(self):
        return nornir_imageregistration.transforms.MeshWithRBFFallback(_mesh_points())

    def _host(self, a) -> np.ndarray:
        return nornir_imageregistration.EnsureNumpyArray(a)

    def test_forward_continues_the_affine_outside_the_hull_without_an_rbf_solve(self):
        model = self._model()
        with _CountRBFSolves() as solves:
            mapped = self._host(mesh_hull_affine.map_points(model, _FAR_SOURCE, forward=True))
        self.assertEqual(solves.count, 0)
        np.testing.assert_allclose(mapped, _FAR_SOURCE @ _AFFINE + _OFFSET, atol=1e-2)

    def test_inverse_continues_the_affine_outside_the_hull(self):
        model = self._model()
        far_target = _FAR_SOURCE @ _AFFINE + _OFFSET
        with _CountRBFSolves() as solves:
            mapped = self._host(mesh_hull_affine.map_points(model, far_target, forward=False))
        self.assertEqual(solves.count, 0)
        np.testing.assert_allclose(mapped, _FAR_SOURCE, atol=1e-2)

    def test_inside_the_hull_is_unchanged(self):
        model = self._model()
        expected = self._host(model.Transform(_INSIDE_SOURCE, extrapolate=False))
        np.testing.assert_array_equal(
            self._host(mesh_hull_affine.map_points(model, _INSIDE_SOURCE, forward=True)), expected)

    def test_tracks_point_edits(self):
        model = self._model()
        mesh_hull_affine.map_points(model, _FAR_SOURCE, forward=True)
        model.TranslateFixed(np.array([10.0, 0.0]))
        np.testing.assert_allclose(
            self._host(mesh_hull_affine.map_points(model, _FAR_SOURCE, forward=True)),
            _FAR_SOURCE @ _AFFINE + _OFFSET + np.array([10.0, 0.0]), atol=1e-2)

    def test_controller_maps_outside_the_hull_during_a_drag(self):
        controller = TransformController(self._model())
        controller._interactive_edit_depth = 1
        try:
            self.assertTrue(controller.interactive_edit_in_progress)
            with _CountRBFSolves() as solves:
                target = self._host(controller.Transform(_FAR_SOURCE, extrapolate=True))
                source = self._host(controller.InverseTransform(target, extrapolate=True))
        finally:
            controller._interactive_edit_depth = 0
        self.assertEqual(solves.count, 0)
        self.assertTrue(np.isfinite(target).all())
        np.testing.assert_allclose(source, _FAR_SOURCE, atol=1e-2)

    def test_tile_mesh_points_outside_the_hull_are_finite(self):
        pairs = self._host(gltiles._find_corresponding_points(
            self._model(), _FAR_SOURCE, forward_transform=True, extrapolate=False))
        self.assertTrue(np.isfinite(pairs).all())
        np.testing.assert_allclose(pairs[:, :2], _FAR_SOURCE @ _AFFINE + _OFFSET, atol=1e-2)


class TestMeshHullAffine(_MeshCases, unittest.TestCase):
    pass


@unittest.skipUnless(HasCupy(), "requires CuPy")
class TestGpuMeshHullAffine(_MeshCases, unittest.TestCase):

    def _model(self):
        import cupy as cp
        return nornir_imageregistration.transforms.MeshWithRBFFallback_GPUComponent(cp.asarray(_mesh_points()))


class TestOtherTransformsUnchanged(unittest.TestCase):

    def test_grid_keeps_its_own_extrapolation(self):
        grid = nornir_imageregistration.ITKGridDivision((600, 600), cell_size=(128, 128), grid_dims=(5, 5))
        grid.TargetPoints = grid.SourcePoints + np.random.default_rng(4).normal(0, 4, grid.SourcePoints.shape)
        model = nornir_imageregistration.transforms.GridWithRBFFallback(grid)
        self.assertFalse(mesh_hull_affine.uses_hull_affine(model))
        far = np.array([[-300.0, -200.0]])
        np.testing.assert_array_equal(
            nornir_imageregistration.EnsureNumpyArray(mesh_hull_affine.map_points(model, far, forward=False)),
            nornir_imageregistration.EnsureNumpyArray(model.InverseTransform(far)))

    def test_rbf_is_not_a_mesh(self):
        points = _mesh_points()
        model = nornir_imageregistration.transforms.TwoWayRBFWithLinearCorrection(points[:, 2:], points[:, :2])
        self.assertFalse(mesh_hull_affine.uses_hull_affine(model))


if __name__ == '__main__':
    unittest.main()
