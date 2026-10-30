"""Tests for Edit > Clear masked points.

`StosState` stores the source-image mask as `FixedImageMaskViewModel` and the target-image mask
as `WarpedImageMaskViewModel`. `ClearPointsOnMask` must test each mask against the control points
of its own image, and the menu handler must hand it the `TransformController` (which owns
`RemovePoints`), not the bare transform.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest import mock

import numpy as np
from nornir_imageregistration.transforms.meshwithrbffallback import MeshWithRBFFallback

import pyre.common
from pyre.controllers.transformcontroller import TransformController
from pyre.ui.windows.stoswindow import StosWindow


def _controller() -> TransformController:
    """Four points: target rows in [0, 100], source rows in [100, 200] (Y, X)."""
    points = np.array([
        [10.0, 10.0, 110.0, 110.0],
        [10.0, 90.0, 110.0, 190.0],
        [90.0, 10.0, 190.0, 110.0],
        [90.0, 90.0, 190.0, 190.0],
    ], dtype=np.float32)
    return TransformController(MeshWithRBFFallback(points))


def _target_mask() -> np.ndarray:
    """Covers target space only; every source point lies outside it."""
    return np.ones((120, 120), dtype=np.uint8)


def _source_mask_hiding_first_point() -> np.ndarray:
    """Covers source space; zero (masked) under the first source point only."""
    mask = np.ones((250, 250), dtype=np.uint8)
    mask[100:120, 100:120] = 0
    return mask


class TestClearPointsOnMask(unittest.TestCase):

    def test_target_mask_keeps_points_inside_target_image(self) -> None:
        controller = _controller()
        pyre.common.ClearPointsOnMask(controller, None, _target_mask())  # type: ignore[arg-type]
        self.assertEqual(controller.TransformModel.points.shape[0], 4)

    def test_source_mask_removes_only_masked_source_point(self) -> None:
        controller = _controller()
        pyre.common.ClearPointsOnMask(controller, _source_mask_hiding_first_point(), None)  # type: ignore[arg-type]
        remaining = controller.TransformModel.SourcePoints
        self.assertEqual(remaining.shape[0], 3)
        self.assertFalse(np.any(np.all(remaining == [110.0, 110.0], axis=1)))

    def test_both_masks(self) -> None:
        controller = _controller()
        pyre.common.ClearPointsOnMask(controller, _source_mask_hiding_first_point(), _target_mask())
        self.assertEqual(controller.TransformModel.points.shape[0], 3)


class TestClearMaskedPointsMenu(unittest.TestCase):

    def test_handler_passes_controller_with_source_then_target_mask(self) -> None:
        controller = _controller()
        source_mask = _source_mask_hiding_first_point()
        target_mask = _target_mask()
        config = SimpleNamespace(
            FixedImageMaskViewModel=SimpleNamespace(Image=source_mask),
            WarpedImageMaskViewModel=SimpleNamespace(Image=target_mask),
        )
        window = SimpleNamespace(_transform_controller=controller)
        with mock.patch("pyre.state.get_current_stos_config", return_value=config):
            StosWindow.onClearMaskedPoints(window)  # type: ignore[arg-type]
        self.assertEqual(controller.TransformModel.points.shape[0], 3)


if __name__ == "__main__":
    unittest.main()
