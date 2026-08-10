"""Tests for Pyre registration job runner cancel/apply guards."""

from __future__ import annotations

import sys
import threading
import time
import unittest

from PyQt6.QtWidgets import QApplication

from nornir_imageregistration.registration_control import RegistrationCancelled
from pyre.qt_eventmanager import init_main_thread_dispatcher
from pyre.registration_job import RegistrationJobRunner


class TestPyreRegistrationJobRunner(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication(sys.argv)
        init_main_thread_dispatcher()

    def _drain(self, runner: RegistrationJobRunner, timeout_s: float = 5.0) -> None:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            self._app.processEvents()
            if not runner.busy:
                for _ in range(10):
                    self._app.processEvents()
                    time.sleep(0.01)
                return
            time.sleep(0.01)
        raise TimeoutError("registration job did not finish")

    def test_cancel_prevents_success_callback(self) -> None:
        runner = RegistrationJobRunner()
        applied: list[object] = []
        cancelled: list[bool] = []

        def worker(cancel_event, progress_callback):
            raise RegistrationCancelled()

        self.assertTrue(runner.submit(
            worker,
            title="cancel-test",
            on_success=lambda result: applied.append(result),
            on_cancelled=lambda: cancelled.append(True),
        ))
        self._drain(runner)
        self.assertEqual(applied, [])
        self.assertEqual(cancelled, [True])

    def test_success_applies_result(self) -> None:
        runner = RegistrationJobRunner()
        applied: list[int] = []

        def worker(cancel_event, progress_callback):
            progress_callback(1, 1, "done")
            return 42

        self.assertTrue(runner.submit(
            worker,
            title="ok-test",
            on_success=lambda result: applied.append(int(result)),
        ))
        self._drain(runner)
        self.assertEqual(applied, [42])

    def test_second_submit_rejected_while_busy(self) -> None:
        runner = RegistrationJobRunner()
        gate = threading.Event()

        def worker(cancel_event, progress_callback):
            gate.wait(timeout=2.0)
            return 1

        self.assertTrue(runner.submit(worker, title="a", on_success=lambda _r: None))
        self.assertFalse(runner.submit(worker, title="b", on_success=lambda _r: None))
        gate.set()
        self._drain(runner)


if __name__ == "__main__":
    unittest.main()
