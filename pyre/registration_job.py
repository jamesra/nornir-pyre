"""Off-UI registration job runner with status-bar progress and cancel."""

from __future__ import annotations

import threading
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Callable, TypeVar

from nornir_imageregistration.registration_control import (
    ProgressCallback,
    RegistrationCancelled,
)
from pyre.qt_eventmanager import init_main_thread_dispatcher, qt_post_to_main

T = TypeVar("T")

WorkerFn = Callable[[threading.Event, ProgressCallback], T]
SuccessFn = Callable[[T], None]
ErrorFn = Callable[[BaseException], None]
CancelledFn = Callable[[], None]
BusyChangedFn = Callable[[bool], None]


class RegistrationJobRunner:
    """Serialize heavy registration jobs on one worker thread with UI progress."""

    _executor: ThreadPoolExecutor
    _generation: int
    _cancel_event: threading.Event | None
    _busy: bool
    _status_bars: list  # CameraStatusBar; avoid circular import typing
    _busy_changed_listeners: list[BusyChangedFn]
    _lock: threading.Lock

    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pyre-reg-job")
        self._generation = 0
        self._cancel_event = None
        self._busy = False
        self._status_bars = []
        self._busy_changed_listeners = []
        self._lock = threading.Lock()

    @property
    def busy(self) -> bool:
        return self._busy

    def register_status_bar(self, status_bar) -> None:
        """Register a CameraStatusBar that should mirror job progress."""
        with self._lock:
            if status_bar not in self._status_bars:
                self._status_bars.append(status_bar)
                status_bar.set_cancel_handler(self.request_cancel)

    def unregister_status_bar(self, status_bar) -> None:
        with self._lock:
            if status_bar in self._status_bars:
                self._status_bars.remove(status_bar)

    def add_busy_changed_listener(self, listener: BusyChangedFn) -> None:
        if listener not in self._busy_changed_listeners:
            self._busy_changed_listeners.append(listener)

    def request_cancel(self) -> None:
        """Signal the in-flight job to stop at the next cooperative checkpoint."""
        event = self._cancel_event
        if event is not None:
            event.set()
        with self._lock:
            bars = list(self._status_bars)
        for bar in bars:
            bar.set_cancel_enabled(False)

    def submit(
            self,
            worker: WorkerFn[T],
            *,
            title: str,
            on_success: SuccessFn[T],
            on_error: ErrorFn | None = None,
            on_cancelled: CancelledFn | None = None,
    ) -> bool:
        """Start *worker* if idle. Returns False when a job is already running."""
        with self._lock:
            if self._busy:
                return False
            self._busy = True
            self._generation += 1
            generation = self._generation
            cancel_event = threading.Event()
            self._cancel_event = cancel_event
            bars = list(self._status_bars)

        for bar in bars:
            bar.show_job(title)
        for listener in list(self._busy_changed_listeners):
            listener(True)

        init_main_thread_dispatcher()

        def progress_cb(current: int, total: int, label: str) -> None:
            def _apply() -> None:
                if generation != self._generation:
                    return
                with self._lock:
                    active_bars = list(self._status_bars)
                for bar in active_bars:
                    bar.set_progress(current, total, label)

            qt_post_to_main(_apply)

        def _run() -> T:
            return worker(cancel_event, progress_cb)

        future = self._executor.submit(_run)
        future.add_done_callback(
            lambda completed: qt_post_to_main(
                self._on_done,
                completed,
                generation,
                on_success,
                on_error,
                on_cancelled,
            ))
        return True

    def _on_done(
            self,
            future: Future,
            generation: int,
            on_success: SuccessFn,
            on_error: ErrorFn | None,
            on_cancelled: CancelledFn | None,
    ) -> None:
        try:
            if generation != self._generation:
                return
            try:
                result = future.result()
            except RegistrationCancelled:
                if on_cancelled is not None:
                    on_cancelled()
                return
            except Exception as exc:
                if on_error is not None:
                    on_error(exc)
                return
            try:
                on_success(result)
            except Exception as exc:
                if on_error is not None:
                    on_error(exc)
                else:
                    raise
        finally:
            if generation == self._generation:
                self._finish_job()

    def _finish_job(self) -> None:
        with self._lock:
            self._busy = False
            self._cancel_event = None
            bars = list(self._status_bars)
        for bar in bars:
            bar.hide_job()
        for listener in list(self._busy_changed_listeners):
            listener(False)


_registration_job_runner: RegistrationJobRunner | None = None


def get_registration_job_runner() -> RegistrationJobRunner:
    """Return the process-wide registration job runner."""
    global _registration_job_runner
    if _registration_job_runner is None:
        _registration_job_runner = RegistrationJobRunner()
    return _registration_job_runner
