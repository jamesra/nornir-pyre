"""Registration results apply on RBF transforms, and the composite view holds still.

* ``TwoWayRBFWithLinearCorrection`` point edits returned None, so ``MovePoint``
  raised while applying every RBF registration: the point moved, the views never
  refreshed, and because the raise skipped the queue pump the status-bar progress
  never cleared.
* Any exception while applying a result must still pump the queue, or the idle
  handler that hides the progress strip never runs.
* Composite ``camera.lookat`` is target display space, so remesh/registration must
  not InverseTransform-rebase the camera (that used to creep the view on Space).
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from nornir_imageregistration.alignment_record import AlignmentRecord
from nornir_imageregistration.transforms import ITransform
from nornir_imageregistration.transforms.meshwithrbffallback import MeshWithRBFFallback
from nornir_imageregistration.transforms.two_way_rbftransform import (
    TwoWayRBFWithLinearCorrection,
)
from pyre.controllers.transformcontroller import TransformController
from pyre.observable import ObservableSet
from pyre.registration_job import get_registration_job_runner
from pyre.views.composite_display import (
    display_lookat_for_composite,
    lookat_from_display_position,
)


def _distorted_points(seed: int = 1) -> np.ndarray:
    """An 8x8 grid of (target y, target x, source y, source x) rows with jitter."""
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(8):
        for j in range(8):
            target = np.array([i * 100.0, j * 100.0])
            source = target + np.array([30.0, -20.0]) + rng.normal(0.0, 8.0, 2)
            rows.append([target[0], target[1], source[0], source[1]])
    return np.array(rows, dtype=np.float64)


def _mesh() -> MeshWithRBFFallback:
    return MeshWithRBFFallback(_distorted_points())


def _rbf() -> TwoWayRBFWithLinearCorrection:
    points = _distorted_points()
    return TwoWayRBFWithLinearCorrection(WarpedPoints=points[:, 2:4].copy(), FixedPoints=points[:, 0:2].copy())


def _controller(model: ITransform) -> TransformController:
    controller = TransformController(model, selected_points=ObservableSet(initial_set=None))
    controller._point_in_view_fn = lambda _index: True
    return controller


def _register(controller: TransformController, index: int, peak: tuple[float, float]) -> None:
    """Queue and apply one alignment inline (no Qt event loop)."""
    def align(**_kwargs: object) -> AlignmentRecord:
        return AlignmentRecord(peak=peak, weight=1.0, angle=0.0)

    with patch("pyre.controllers.transformcontroller.QApplication") as qapp:
        qapp.instance.return_value = None
        controller.enqueue_point_registrations([index], align_fn=align, alignment_area=np.array([64, 64]))


class TestRegistrationApply(unittest.TestCase):
    """Applied results move the point and the progress strip clears."""

    def setUp(self) -> None:
        get_registration_job_runner().clear_point_queue()

    def tearDown(self) -> None:
        get_registration_job_runner().clear_point_queue()

    def test_rbf_registration_moves_point_and_clears_progress(self) -> None:
        controller = _controller(_rbf())
        before = np.array(controller.TargetPoints[27], dtype=np.float64)
        _register(controller, 27, (1.5, -2.0))
        after = np.array(controller.TargetPoints[27], dtype=np.float64)
        np.testing.assert_allclose(after - before, [1.5, -2.0], atol=1e-4)
        self.assertTrue(controller._registration_queue.is_idle)
        self.assertIsNone(get_registration_job_runner().active_text)

    def test_failed_apply_still_clears_progress(self) -> None:
        controller = _controller(_mesh())
        with patch.object(controller, "_apply_registration_record", side_effect=RuntimeError("boom")), \
                self.assertRaises(RuntimeError):
            _register(controller, 27, (1.0, 1.0))
        self.assertTrue(controller._registration_queue.is_idle)
        self.assertIsNone(get_registration_job_runner().active_text,
                          "the strip must hide even when applying a result raised")


class TestCompositeRebaseHoldsDisplay(unittest.TestCase):
    """Repeated applies leave the composite display center where it was."""

    def _run(self, model: ITransform) -> np.ndarray:
        controller = _controller(model)
        camera = SimpleNamespace(lookat=np.array([380.0, 330.0]), visible_world_size=None)

        def on_change(changed: TransformController, *_args: object, **_kwargs: object) -> None:
            # Panel drops legacy pending preserve; lookat stays display-native.
            changed.consume_pending_composite_display_preserve()

        controller.AddOnChangeEventListener(on_change)
        start = display_lookat_for_composite(camera, controller).copy()
        rng = np.random.default_rng(5)
        for _ in range(20):
            _register(controller, 27, (float(rng.normal(0.0, 3.0)), float(rng.normal(0.0, 3.0))))
            display_lookat_for_composite(camera, controller)  # a paint between results
        return display_lookat_for_composite(camera, controller) - start

    def test_mesh_display_does_not_drift(self) -> None:
        np.testing.assert_allclose(self._run(_mesh()), [0.0, 0.0], atol=1e-6)

    def test_rbf_display_does_not_drift(self) -> None:
        np.testing.assert_allclose(self._run(_rbf()), [0.0, 0.0], atol=1e-6)


class TestDisplayLookatIdentity(unittest.TestCase):
    """``lookat_from_display_position`` is identity for display-native cameras."""

    def test_returns_display_point(self) -> None:
        controller = _controller(_mesh())
        display = np.array([123.0, 456.0], dtype=np.float64)
        lookat = lookat_from_display_position(controller, display)
        np.testing.assert_allclose(lookat, display)


if __name__ == "__main__":
    unittest.main()
