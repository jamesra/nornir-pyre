"""SetPoints must accept the CuPy snapshots that copy_points returns for GPU models.

``copy_points`` deep-copies the live ``points`` array, which is a CuPy array for
``*_GPUComponent`` transforms. Undo and command cancel restore that snapshot through
``SetPoints``, which only accepted NumPy and raised "points parameter has unexpected
type: cupy.ndarray". Converting the transform type cancels the active command, so the
convert dialog reported failure, and a cancelled point drag could not restore points.
"""
from __future__ import annotations

import unittest

import nornir_imageregistration
import numpy as np
from nornir_imageregistration.computational_lib import HasCupy
from nornir_imageregistration.transforms import TwoWayRBFWithLinearCorrection
from pyre.controllers.transformcontroller import TransformController
from pyre.space import Space


def _points() -> np.ndarray:
    fixed = np.array([[i * 100.0, j * 100.0] for i in range(3) for j in range(3)])
    return np.hstack([fixed, fixed + np.array([5.0, -3.0])])


@unittest.skipUnless(HasCupy(), "requires CuPy")
class TestSetPointsAcceptsDeviceSnapshot(unittest.TestCase):

    def test_gpu_mesh_restores_its_own_snapshot(self) -> None:
        import cupy as cp
        model = nornir_imageregistration.transforms.MeshWithRBFFallback_GPUComponent(cp.asarray(_points()))
        controller = TransformController(model)
        snapshot = controller.copy_points()
        self.assertIsInstance(snapshot, cp.ndarray)
        controller.MovePoint(4, ImageDX=7.0, ImageDY=-3.0, space=Space.Target)
        controller.SetPoints(snapshot)
        np.testing.assert_allclose(
            nornir_imageregistration.EnsureNumpyArray(controller.copy_points()),
            _points())

    def test_host_model_accepts_device_snapshot(self) -> None:
        import cupy as cp
        points = _points()
        controller = TransformController(
            TwoWayRBFWithLinearCorrection(points[:, 2:], points[:, :2]))
        controller.MovePoint(4, ImageDX=7.0, ImageDY=-3.0, space=Space.Target)
        controller.SetPoints(cp.asarray(points))
        restored = controller.copy_points()
        self.assertIsInstance(restored, np.ndarray)
        np.testing.assert_allclose(restored, points)


if __name__ == '__main__':
    unittest.main()
