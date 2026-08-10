"""Tests for TransformController.TransformModel replace / same-object refresh."""

from __future__ import annotations

import unittest

import numpy as np
from nornir_imageregistration.transforms import MeshWithRBFFallback

from pyre.controllers.transformcontroller import TransformController


def _mesh() -> MeshWithRBFFallback:
    points = np.array([
        [0.0, 0.0, 100.0, 100.0],
        [0.0, 100.0, 100.0, 200.0],
        [100.0, 0.0, 200.0, 100.0],
        [100.0, 100.0, 200.0, 200.0],
    ], dtype=np.float64)
    return MeshWithRBFFallback(points)


class TestTransformModelReplace(unittest.TestCase):
    def test_new_model_fires_replaced_and_change(self) -> None:
        controller = TransformController(_mesh())
        replaced: list[object] = []
        changed: list[object] = []
        controller.AddOnModelReplacedEventListener(
            lambda c, old, new: replaced.append((old, new)))
        controller.AddOnChangeEventListener(lambda c: changed.append(c))

        new_model = _mesh()
        controller.TransformModel = new_model

        self.assertEqual(len(replaced), 1)
        self.assertIs(replaced[0][1], new_model)
        self.assertGreaterEqual(len(changed), 1)

    def test_same_object_reassign_still_fires_change(self) -> None:
        """Refine often returns the transform it mutated; UI must still refresh."""
        model = _mesh()
        controller = TransformController(model)
        replaced: list[object] = []
        changed: list[object] = []
        controller.AddOnModelReplacedEventListener(
            lambda c, old, new: replaced.append((old, new)))
        controller.AddOnChangeEventListener(lambda c: changed.append(c))

        # Mutate in place the way RefineTransform / TranslateFixed can.
        points = np.asarray(model.points, dtype=np.float64).copy()
        points[:, 0:2] += 5.0
        model.points = points

        controller.TransformModel = model

        self.assertEqual(replaced, [], "same identity should not look like a replace")
        self.assertGreaterEqual(len(changed), 1)
        np.testing.assert_allclose(controller.points[:, 0:2], points[:, 0:2], atol=1e-5)

    def test_apply_external_transform_forces_replace_and_change(self) -> None:
        model = _mesh()
        controller = TransformController(model)
        replaced: list[object] = []
        changed: list[object] = []
        controller.AddOnModelReplacedEventListener(
            lambda c, old, new: replaced.append((old, new)))
        controller.AddOnChangeEventListener(lambda c: changed.append(c))

        # Simulate a stuck coalesced-change flag from a bad worker-thread notify.
        controller._change_event_pending = True

        points = np.asarray(model.points, dtype=np.float64).copy()
        points[:, 0:2] += 12.0
        model.points = points
        controller.apply_external_transform(model)

        self.assertEqual(len(replaced), 1)
        self.assertIsNone(replaced[0][0])
        self.assertIs(replaced[0][1], model)
        self.assertGreaterEqual(len(changed), 1)
        self.assertFalse(controller._change_event_pending)
        np.testing.assert_allclose(controller.points[:, 0:2], points[:, 0:2], atol=1e-5)

    def test_apply_external_transform_replaces_with_new_model(self) -> None:
        controller = TransformController(_mesh())
        new_model = _mesh()
        controller.apply_external_transform(new_model)
        self.assertIs(controller.TransformModel, new_model)


if __name__ == "__main__":
    unittest.main()
