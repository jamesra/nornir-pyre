"""Shared status-bar progress strip, one Cancel for every long task, and Escape routing.

Covers the job runner's activity strip (job and control-point queue), the
controller's queue progress and user cancel, the stale-epoch cancelled-ID leak,
the real ``CameraStatusBar`` progress widget, and the Escape claim filter.
Runs headless (``QT_QPA_PLATFORM=offscreen`` / ``NORNIR_HEADLESS``).
"""

from __future__ import annotations

import os
import sys
import threading
import time
import unittest
from typing import Any
from unittest.mock import MagicMock, patch

import numpy as np
from nornir_imageregistration.alignment_record import AlignmentRecord
from nornir_imageregistration.transforms.meshwithrbffallback import MeshWithRBFFallback
from PyQt6.QtCore import QEvent, Qt, QThread
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication, QWidget

from pyre.controllers.transformcontroller import TransformController, _mapped_yx_host
from pyre.qt_eventmanager import init_main_thread_dispatcher
from pyre.registration_job import RegistrationJobRunner, get_registration_job_runner
from pyre.ui.escape_claim import EscapeClaimFilter, command_claims_escape

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class _FakeStatusBar:
    """Records what the runner pushes to a CameraStatusBar."""

    text: str | None
    current: int
    total: int
    cancel_enabled: bool
    cancel_handler: Any

    def __init__(self) -> None:
        self.text = None
        self.current = 0
        self.total = 0
        self.cancel_enabled = True
        self.cancel_handler = None

    def set_cancel_handler(self, handler: Any) -> None:
        self.cancel_handler = handler

    def set_cancel_enabled(self, enabled: bool) -> None:
        self.cancel_enabled = enabled

    def show_activity(self, text: str, current: int, total: int, cancel_enabled: bool = True) -> None:
        self.text, self.current, self.total, self.cancel_enabled = text, current, total, cancel_enabled

    def hide_activity(self) -> None:
        self.text = None

    def press_cancel(self) -> None:
        assert self.cancel_handler is not None
        self.cancel_handler()


def _app() -> QApplication:
    app = QApplication.instance() or QApplication(sys.argv)
    init_main_thread_dispatcher()
    return app  # type: ignore[return-value]


def _process_until(app: QApplication, predicate: Any, timeout_s: float = 5.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(0.01)
    raise TimeoutError("condition not reached")


def _mesh(n_points: int = 6) -> MeshWithRBFFallback:
    points = np.array(
        [[float(i * 10), float(i * 20), float(i * 100), float(i * 200)] for i in range(n_points)],
        dtype=np.float64)
    return MeshWithRBFFallback(points)


def _fake_qapp() -> MagicMock:
    app = MagicMock()
    app.thread.return_value = QThread.currentThread()
    return app


class TestActivityStrip(unittest.TestCase):
    """Text, counts and Cancel state the runner pushes to status bars."""

    app: QApplication

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _app()

    def setUp(self) -> None:
        self.runner = RegistrationJobRunner()
        self.bar = _FakeStatusBar()
        self.runner.register_status_bar(self.bar)

    def _start_job(self, title: str, gate: threading.Event,
                   progress: tuple[int, int, str] | None = None) -> None:
        def worker(cancel_event: threading.Event, progress_callback: Any) -> int:
            if progress is not None:
                progress_callback(*progress)
            while not gate.wait(timeout=0.01):
                if cancel_event.is_set():
                    break
            return 1

        self.assertTrue(self.runner.submit(worker, title=title, on_success=lambda _r: None))

    def _finish_job(self, gate: threading.Event) -> None:
        gate.set()
        _process_until(self.app, lambda: not self.runner.busy)

    def test_point_queue_text_and_counts(self) -> None:
        self.assertIsNone(self.bar.text)
        self.runner.report_point_queue(3, 12)
        self.assertEqual(self.bar.text, "Registering control points 3 / 12")
        self.assertEqual((self.bar.current, self.bar.total), (3, 12))
        self.assertTrue(self.bar.cancel_enabled)
        self.runner.report_point_queue(0, 0)
        self.assertIsNone(self.bar.text)

    def test_job_title_plus_progress_label(self) -> None:
        gate = threading.Event()
        self._start_job("Refine w/ Grid", gate, (2, 5, "pass 2 / 5"))
        _process_until(self.app, lambda: self.bar.text == "Refine w/ Grid: pass 2 / 5")
        self.assertEqual((self.bar.current, self.bar.total), (2, 5))
        self._finish_job(gate)
        self.assertIsNone(self.bar.text)

    def test_most_recently_started_task_owns_the_text(self) -> None:
        gate = threading.Event()
        self._start_job("Refine w/ Grid", gate)
        self.assertEqual(self.bar.text, "Refine w/ Grid")
        self.runner.report_point_queue(0, 4)
        self.assertEqual(self.bar.text, "Registering control points 0 / 4")
        self.runner.report_point_queue(1, 4)
        self.assertEqual(self.bar.text, "Registering control points 1 / 4")
        self.runner.clear_point_queue()
        self.assertEqual(self.bar.text, "Refine w/ Grid")
        self._finish_job(gate)

    def test_job_started_after_queue_takes_the_text(self) -> None:
        gate = threading.Event()
        self.runner.report_point_queue(1, 3)
        self._start_job("Rotate translate estimate", gate)
        self.assertEqual(self.bar.text, "Rotate translate estimate")
        self._finish_job(gate)
        self.assertEqual(self.bar.text, "Registering control points 1 / 3")
        self.runner.clear_point_queue()

    def test_status_bar_cancel_stops_job_and_point_queue(self) -> None:
        gate = threading.Event()
        cancelled_queues: list[bool] = []
        self.runner.add_cancel_listener(lambda: cancelled_queues.append(True))
        self._start_job("Refine w/ Grid", gate)
        self.runner.report_point_queue(0, 2)
        self.bar.press_cancel()
        self.assertEqual(cancelled_queues, [True])
        # The point queue is still on screen until its owner clears it, so Cancel stays live.
        self.assertTrue(self.bar.cancel_enabled)
        self.runner.clear_point_queue()
        # Only the job remains and it has already been asked to stop.
        self.assertFalse(self.bar.cancel_enabled)
        _process_until(self.app, lambda: not self.runner.busy)
        self.assertIsNone(self.bar.text)

    def test_deleted_status_bar_is_dropped(self) -> None:
        dead = MagicMock()
        dead.show_activity.side_effect = RuntimeError("wrapped C/C++ object has been deleted")
        self.runner.register_status_bar(dead)
        self.runner.report_point_queue(1, 2)
        self.assertNotIn(dead, self.runner._status_bars)
        self.assertEqual(self.bar.text, "Registering control points 1 / 2")


class TestControllerQueueProgressAndCancel(unittest.TestCase):
    """The controller reports finished / queued and cancels on request."""

    def setUp(self) -> None:
        self.runner = get_registration_job_runner()
        self.runner.clear_point_queue()
        self.controller = TransformController(_mesh(6))
        self.pool = MagicMock()
        self.pool.max_workers = 2

    def tearDown(self) -> None:
        self.runner.clear_point_queue()

    def _enqueue(self, indices: list[int]) -> list[int]:
        with patch("pyre.controllers.transformcontroller.QApplication") as qapp, \
                patch("pyre.controllers.transformcontroller.pools.GetGlobalThreadPool",
                      return_value=self.pool):
            qapp.instance.return_value = _fake_qapp()
            return self.controller.enqueue_point_registrations(
                indices, align_fn=lambda **_: AlignmentRecord(peak=(1.0, 1.0), weight=1.0, angle=0.0))

    def _finish(self, index: int, record: AlignmentRecord | None = None, epoch: int | None = None) -> None:
        point_id = self.controller.point_id_for_index(index)
        assert point_id is not None
        snapshot = _mapped_yx_host(self.controller.GetFixedPoint(index)).copy()
        with patch("pyre.controllers.transformcontroller.QApplication") as qapp, \
                patch("pyre.controllers.transformcontroller.pools.GetGlobalThreadPool",
                      return_value=self.pool):
            qapp.instance.return_value = _fake_qapp()
            self.controller._on_registration_finished(point_id, snapshot, record, epoch)

    def test_progress_counts_finished_over_queued_since_idle(self) -> None:
        self._enqueue([0, 1, 2])
        self.assertEqual(self.runner.active_text, "Registering control points 0 / 3")
        self._finish(0)
        self.assertEqual(self.runner.active_text, "Registering control points 1 / 3")
        self._enqueue([3])
        self.assertEqual(self.runner.active_text, "Registering control points 1 / 4")
        for index in (1, 2, 3):
            self._finish(index)
        self.assertIsNone(self.runner.active_text, "the strip hides once the queue is idle")
        self._enqueue([4])
        self.assertEqual(self.runner.active_text, "Registering control points 0 / 1",
                         "a new batch starts counting from zero")

    def test_cancel_drops_queue_keeps_applied_points_and_discards_late_results(self) -> None:
        self._enqueue([0, 1, 2, 3])
        epoch = self.controller._registration_epoch
        self._finish(0, AlignmentRecord(peak=(1.0, 1.0), weight=1.0, angle=0.0), epoch)
        applied = np.asarray(self.controller.TargetPoints[0], dtype=np.float64).copy()
        busy_events: list[frozenset[int]] = []
        self.controller.AddOnBusyPointsChanged(lambda _c, ids: busy_events.append(frozenset(ids)))
        in_flight = set(self.controller._registration_queue.in_flight_ids)
        self.assertTrue(in_flight)

        self.controller.cancel_point_registrations()

        self.assertTrue(self.controller._registration_queue.is_idle)
        self.assertEqual(self.controller.busy_point_ids, frozenset())
        self.assertIsNone(self.runner.active_text)
        self.assertTrue(busy_events, "busy-changed must fire so glyphs clear")
        self.assertFalse(self.controller._registration_reselect_ids)
        np.testing.assert_allclose(self.controller.TargetPoints[0], applied)

        # A worker that was still running reports after the cancel: discarded.
        late_id = next(iter(in_flight))
        late_index = self.controller.index_for_point_id(late_id)
        assert late_index is not None
        before = np.asarray(self.controller.points, dtype=np.float64).copy()
        self._finish(late_index, AlignmentRecord(peak=(5.0, 5.0), weight=1.0, angle=0.0), epoch)
        np.testing.assert_allclose(self.controller.points, before)
        self.assertFalse(self.controller._registration_queue.is_cancelled(late_id),
                         "a stale-epoch callback must not leave its ID marked cancelled")

    def test_cancel_with_nothing_queued_is_harmless(self) -> None:
        self.controller.cancel_point_registrations()
        self.assertTrue(self.controller._registration_queue.is_idle)
        self.assertIsNone(self.runner.active_text)

    def test_stale_epoch_callback_keeps_mark_for_requeued_point(self) -> None:
        self._enqueue([0])
        point_id = self.controller.point_id_for_index(0)
        assert point_id is not None
        old_epoch = self.controller._registration_epoch
        self.controller.cancel_point_registrations()
        self._enqueue([0])  # queued again in the new epoch, in flight
        self.controller._registration_queue.cancel(point_id)  # e.g. point deleted
        self._finish(0, None, old_epoch)  # the old job reports late
        self.assertTrue(self.controller._registration_queue.is_cancelled(point_id),
                        "the new job's cancel mark belongs to the new job")


class TestCameraStatusBarProgress(unittest.TestCase):
    """The real widget draws the task text centred over a determinate bar."""

    app: QApplication

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _app()

    def setUp(self) -> None:
        from pyre.ui.widgets.camerastatusbar import CameraStatusBar

        self.parent = QWidget()
        self.bar = CameraStatusBar(self.parent, camera=MagicMock(scale=1.0), camera_window=self.parent,
                                   mouse_position_history_manager=MagicMock())

    def tearDown(self) -> None:
        get_registration_job_runner().unregister_status_bar(self.bar)
        self.parent.deleteLater()

    def test_show_and_hide_activity(self) -> None:
        self.assertFalse(self.bar.activity_visible)
        self.bar.show_activity("Registering control points 3 / 12", 3, 12)
        self.assertTrue(self.bar.activity_visible)
        self.assertEqual(self.bar.activity_text, "Registering control points 3 / 12")
        self.assertEqual((self.bar.progress_value, self.bar.progress_maximum), (3, 12))
        progress = self.bar._job_progress
        self.assertTrue(progress.isTextVisible())
        self.assertEqual(progress.text(), "Registering control points 3 / 12")
        self.assertTrue(progress.alignment() & Qt.AlignmentFlag.AlignHCenter)
        self.assertTrue(self.bar.cancel_enabled)

        self.bar.show_activity("Refine w/ Grid", 0, 0, cancel_enabled=False)
        self.assertEqual(progress.text(), "Refine w/ Grid", "text stays visible before the first count")
        self.assertGreater(self.bar.progress_maximum, self.bar.progress_value)
        self.assertFalse(self.bar.cancel_enabled)

        self.bar.hide_activity()
        self.assertFalse(self.bar.activity_visible)
        self.assertEqual(self.bar.activity_text, "")

    def test_cancel_button_calls_handler(self) -> None:
        calls: list[bool] = []
        self.bar.set_cancel_handler(lambda: calls.append(True))
        self.bar.show_activity("Registering control points 0 / 1", 0, 1)
        self.bar._job_cancel.click()
        self.assertEqual(calls, [True])

    def test_global_runner_drives_the_widget(self) -> None:
        runner = get_registration_job_runner()
        runner.report_point_queue(2, 5)
        try:
            self.assertEqual(self.bar.activity_text, "Registering control points 2 / 5")
            self.assertEqual(self.bar.progress_value, 2)
        finally:
            runner.clear_point_queue()
        self.assertFalse(self.bar.activity_visible)


class TestEscapeClaim(unittest.TestCase):
    """Escape reaches commands that use it; otherwise the window cancel shortcut gets it."""

    app: QApplication

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _app()

    def _override(self, key: Qt.Key) -> QKeyEvent:
        event = QKeyEvent(QEvent.Type.ShortcutOverride, key, Qt.KeyboardModifier.NoModifier)
        event.ignore()
        return event

    def test_commands_that_use_escape_claim_it(self) -> None:
        from pyre.commands.defaulttransformcommand import DefaultTransformCommand
        from pyre.commands.stos.createcontrolpointcommand import (
            CreateControlPointCommand,
        )
        from pyre.commands.stos.regionselectcommand import RegionSelectCommand
        from pyre.commands.stos.translaterigidcommand import (
            ManipulateRigidTransformCommand,
        )

        self.assertTrue(command_claims_escape(object.__new__(CreateControlPointCommand)))
        self.assertTrue(command_claims_escape(object.__new__(RegionSelectCommand)))
        self.assertFalse(command_claims_escape(object.__new__(DefaultTransformCommand)))
        # A rigid drag does not use Escape (cancel is a mouse gesture), so Escape cancels registrations.
        self.assertFalse(command_claims_escape(object.__new__(ManipulateRigidTransformCommand)))
        self.assertFalse(command_claims_escape(None))

    def test_filter_accepts_escape_override_only_for_claiming_command(self) -> None:
        widget = QWidget()
        active: list[object | None] = [None]
        event_filter = EscapeClaimFilter(lambda: active[0], widget)

        event = self._override(Qt.Key.Key_Escape)
        self.assertFalse(event_filter.eventFilter(widget, event))
        self.assertFalse(event.isAccepted(), "no command: the window shortcut must fire")

        active[0] = MagicMock(claims_escape=True)
        event = self._override(Qt.Key.Key_Escape)
        self.assertTrue(event_filter.eventFilter(widget, event))
        self.assertTrue(event.isAccepted(), "the command keeps Escape")

        event = self._override(Qt.Key.Key_Space)
        self.assertFalse(event_filter.eventFilter(widget, event))
        self.assertFalse(event.isAccepted(), "other keys are untouched")
        widget.deleteLater()

    def test_window_cancel_calls_queue_and_job_cancel(self) -> None:
        from pyre.ui.windows.stoswindow import StosWindow

        window = MagicMock()
        runner = MagicMock()
        with patch("pyre.ui.windows.stoswindow.get_registration_job_runner", return_value=runner):
            StosWindow.cancel_all_long_running(window)
        window._transform_controller.cancel_point_registrations.assert_called_once()
        runner.request_cancel.assert_called_once()


if __name__ == "__main__":
    unittest.main()
