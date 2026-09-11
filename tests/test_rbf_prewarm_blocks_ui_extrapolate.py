"""RBF prewarm must not let UI extrapolate=True rebuild weights on the GUI thread."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import numpy as np
from nornir_imageregistration.transforms import Rigid

from pyre.controllers.transformcontroller import TransformController


class TestRbfPrewarmBlocksUiExtrapolation(unittest.TestCase):
    def test_transform_forces_extrapolate_false_while_prewarm_pending(self) -> None:
        controller = TransformController(
            Rigid(target_offset=(0.0, 0.0), source_rotation_center=(0.0, 0.0), angle=0.0))
        controller._rbf_prewarm_ready = False
        captured: dict[str, object] = {}

        def _capture(points, **kwargs):
            captured.update(kwargs)
            return np.asarray(points, dtype=np.float64)

        with patch.object(controller.TransformModel, "Transform", side_effect=_capture):
            controller.Transform(np.array([[1.0, 2.0]]), extrapolate=True)
        self.assertFalse(captured.get("extrapolate", True))

    def test_inverse_transform_forces_extrapolate_false_while_prewarm_pending(self) -> None:
        controller = TransformController(
            Rigid(target_offset=(0.0, 0.0), source_rotation_center=(0.0, 0.0), angle=0.0))
        controller._rbf_prewarm_ready = False
        captured: dict[str, object] = {}

        def _capture(points, **kwargs):
            captured.update(kwargs)
            return np.asarray(points, dtype=np.float64)

        with patch.object(controller.TransformModel, "InverseTransform", side_effect=_capture):
            controller.InverseTransform(np.array([[1.0, 2.0]]), extrapolate=True)
        self.assertFalse(captured.get("extrapolate", True))


if __name__ == "__main__":
    unittest.main()
