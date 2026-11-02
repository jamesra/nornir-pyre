"""Spacebar registration queue: one Ctrl+Z for the whole batch (or cancel mid-way)."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import numpy as np
from nornir_imageregistration.alignment_record import AlignmentRecord
from nornir_imageregistration.transforms.meshwithrbffallback import MeshWithRBFFallback
from pyre.controllers.transformcontroller import TransformController
from pyre.observable import ObservableSet
from pyre.registration_job import get_registration_job_runner


def _mesh(n_points: int = 4) -> MeshWithRBFFallback:
    points = np.array(
        [
            [float(i * 10), float(i * 20), float(i * 100), float(i * 200)]
            for i in range(n_points)
        ],
        dtype=np.float64,
    )
    return MeshWithRBFFallback(points)


def _controller() -> TransformController:
    controller = TransformController(_mesh(), selected_points=ObservableSet(initial_set=None))
    controller._point_in_view_fn = lambda _index: True
    return controller


def _align_peak(peak: tuple[float, float]):
    def align(**_kwargs: object) -> AlignmentRecord:
        return AlignmentRecord(peak=peak, weight=1.0, angle=0.0)

    return align


def _patch_commit_to_capture(controller: TransformController, saves: list[np.ndarray]):
    """Replace DI-backed commit with a spy that records the pre-batch snapshot."""

    def _commit() -> None:
        snapshot = controller._registration_batch_undo_points
        had = controller._registration_batch_had_apply
        controller._registration_batch_undo_points = None
        controller._registration_batch_had_apply = False
        if snapshot is None or not had:
            return
        saves.append(np.asarray(snapshot, dtype=np.float64).copy())

    return patch.object(controller, "_commit_registration_batch_undo", side_effect=_commit)


class TestRegistrationBatchUndo(unittest.TestCase):
    def setUp(self) -> None:
        get_registration_job_runner().clear_point_queue()

    def test_batch_of_two_pushes_one_undo_of_pre_batch_points(self) -> None:
        controller = _controller()
        before = controller.copy_points()
        saves: list[np.ndarray] = []

        with patch("pyre.controllers.transformcontroller.QApplication") as qapp, \
                _patch_commit_to_capture(controller, saves):
            qapp.instance.return_value = None
            controller.enqueue_point_registrations(
                [0, 1],
                align_fn=_align_peak((1.0, 2.0)),
                alignment_area=np.array([16, 16], dtype=np.int32),
            )

        self.assertEqual(len(saves), 1)
        np.testing.assert_allclose(saves[0], before)
        self.assertFalse(np.allclose(controller.copy_points(), before))
        self.assertIsNone(controller._registration_batch_undo_points)

    def test_cancel_mid_batch_still_one_undo_for_applied_points(self) -> None:
        controller = _controller()
        before = controller.copy_points()
        saves: list[np.ndarray] = []

        controller._registration_batch_undo_points = before.copy()
        controller._registration_batch_had_apply = False
        controller._registration_batch_total = 2
        record = AlignmentRecord(peak=(5.0, 6.0), weight=1.0, angle=0.0)
        point_id = controller.point_id_for_index(0)
        assert point_id is not None
        snapshot_target = np.asarray(controller.TargetPoints[0], dtype=np.float64).copy()
        controller._apply_registration_record(point_id, snapshot_target, record)
        self.assertTrue(controller._registration_batch_had_apply)

        with _patch_commit_to_capture(controller, saves):
            controller.cancel_point_registrations()

        self.assertEqual(len(saves), 1)
        np.testing.assert_allclose(saves[0], before)
        self.assertFalse(np.allclose(controller.copy_points(), before))

    def test_no_undo_when_nothing_applied(self) -> None:
        controller = _controller()
        controller._registration_batch_undo_points = controller.copy_points()
        controller._registration_batch_had_apply = False
        with patch("pyre.commands.transform_undo.save_points_undo") as save_undo:
            controller._commit_registration_batch_undo()
            save_undo.assert_not_called()
        self.assertIsNone(controller._registration_batch_undo_points)

    def test_holding_space_extends_same_batch_snapshot(self) -> None:
        """A second enqueue while the queue is still busy keeps the first snapshot."""
        controller = _controller()
        first = controller.copy_points()
        controller._registration_batch_undo_points = first.copy()
        controller._registration_batch_had_apply = True
        controller._registration_batch_total = 1
        # Simulate a still-busy queue so a second enqueue does not start a new batch.
        controller._registration_queue.enqueue([controller.point_id_for_index(0)])
        with patch("pyre.controllers.transformcontroller.QApplication") as qapp, \
                patch.object(controller, "_pump_registration_queue"):
            qapp.instance.return_value = None
            controller.enqueue_point_registrations(
                [1],
                align_fn=_align_peak((1.0, 2.0)),
                alignment_area=np.array([16, 16], dtype=np.int32),
            )
        np.testing.assert_allclose(controller._registration_batch_undo_points, first)
        self.assertEqual(controller._registration_batch_total, 2)


if __name__ == "__main__":
    unittest.main()
