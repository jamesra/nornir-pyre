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

    def test_on_preview_posted_to_main_thread(self) -> None:
        runner = RegistrationJobRunner()
        previews: list[object] = []
        applied: list[object] = []
        main_thread = threading.get_ident()
        preview_threads: list[int] = []

        def worker(cancel_event, progress_callback):
            progress_callback(1, 2, "a", "first")
            progress_callback(2, 2, "b", "second")
            return "done"

        def on_preview(payload: object) -> None:
            preview_threads.append(threading.get_ident())
            previews.append(payload)

        self.assertTrue(runner.submit(
            worker,
            title="preview-test",
            on_success=lambda result: applied.append(result),
            on_preview=on_preview,
        ))
        self._drain(runner)
        self.assertEqual(applied, ["done"])
        self.assertTrue(previews)
        self.assertEqual(previews[-1], "second")
        self.assertTrue(all(thread_id == main_thread for thread_id in preview_threads))

    def test_on_preview_applies_each_pass_when_gui_keeps_up(self) -> None:
        """Spaced RefineTransform-style previews each reach on_preview."""
        runner = RegistrationJobRunner()
        previews: list[object] = []
        applied: list[object] = []
        pass_applied = threading.Event()

        def worker(cancel_event, progress_callback):
            for i in range(1, 4):
                pass_applied.clear()
                progress_callback(i, 3, f"Refine pass {i}/3", f"pass-{i}")
                if not pass_applied.wait(timeout=2.0):
                    raise TimeoutError(f"preview for pass {i} was not applied")
            return "done"

        def on_preview(payload: object) -> None:
            previews.append(payload)
            pass_applied.set()

        self.assertTrue(runner.submit(
            worker,
            title="spaced-preview-test",
            on_success=lambda result: applied.append(result),
            on_preview=on_preview,
        ))
        self._drain(runner)
        self.assertEqual(applied, ["done"])
        self.assertEqual(previews, ["pass-1", "pass-2", "pass-3"])

    def test_cancel_keeps_preview_already_posted(self) -> None:
        runner = RegistrationJobRunner()
        previews: list[object] = []

        def worker(cancel_event, progress_callback):
            progress_callback(1, 1, "pass", "kept")
            raise RegistrationCancelled()

        self.assertTrue(runner.submit(
            worker,
            title="cancel-preview",
            on_success=lambda _r: None,
            on_cancelled=lambda: None,
            on_preview=lambda payload: previews.append(payload),
        ))
        self._drain(runner)
        self.assertEqual(previews[-1], "kept")


if __name__ == "__main__":
    unittest.main()
