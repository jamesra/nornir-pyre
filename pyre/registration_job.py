"""Off-UI registration job runner with status-bar progress and cancel."""

from __future__ import annotations

import logging
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable, TypedDict, TypeVar

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
PreviewFn = Callable[[object], None]
CancelListenerFn = Callable[[], None]

POINT_QUEUE_TITLE = "Registering control points"

_logger = logging.getLogger(__name__)


@dataclass
class _Activity:
    """One long-running task shown in the shared status-bar strip."""

    text: str
    current: int
    total: int
    started: int  # Start order; the most recently started activity is shown


def format_job_text(title: str, label: str, current: int, total: int) -> str:
    """Status text for a job: the title plus its progress label, or plain counts."""
    if label:
        return f"{title}: {label}"
    if total > 0:
        return f"{title} {current} / {total}"
    return title


def format_point_queue_text(finished: int, total: int) -> str:
    """Status text for the control-point registration queue."""
    return f"{POINT_QUEUE_TITLE} {finished} / {total}"


class _PreviewState(TypedDict):
    seq: int
    value: object | None


class RegistrationJobRunner:
    """Serialize heavy registration jobs on one worker thread with UI progress.

    Also owns the shared status-bar strip: a running job and the control-point
    registration queue (reported by the transform controller) both show there,
    with the most recently started one's text, and one Cancel stops both.
    """

    _executor: ThreadPoolExecutor
    _generation: int
    _cancel_event: threading.Event | None
    _busy: bool
    _status_bars: list  # CameraStatusBar; avoid circular import typing
    _busy_changed_listeners: list[BusyChangedFn]
    _cancel_listeners: list[CancelListenerFn]
    _lock: threading.Lock
    _job_activity: _Activity | None
    _point_activity: _Activity | None
    _activity_counter: int
    _job_cancel_requested: bool

    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pyre-reg-job")
        self._generation = 0
        self._cancel_event = None
        self._busy = False
        self._status_bars = []
        self._busy_changed_listeners = []
        self._cancel_listeners = []
        self._lock = threading.Lock()
        self._job_activity = None
        self._point_activity = None
        self._activity_counter = 0
        self._job_cancel_requested = False

    @property
    def busy(self) -> bool:
        return self._busy

    @property
    def active_text(self) -> str | None:
        """Text the status-bar strip shows now, or None when it is hidden."""
        activity = self._shown_activity()
        return None if activity is None else activity.text

    def register_status_bar(self, status_bar) -> None:
        """Register a CameraStatusBar that should mirror job and point-queue progress."""
        with self._lock:
            if status_bar not in self._status_bars:
                self._status_bars.append(status_bar)
                status_bar.set_cancel_handler(self.cancel_all)
        self._refresh_status_bars()

    def unregister_status_bar(self, status_bar) -> None:
        with self._lock:
            if status_bar in self._status_bars:
                self._status_bars.remove(status_bar)

    def add_busy_changed_listener(self, listener: BusyChangedFn) -> None:
        if listener not in self._busy_changed_listeners:
            self._busy_changed_listeners.append(listener)

    def add_cancel_listener(self, listener: CancelListenerFn) -> None:
        """Call *listener* when the status-bar Cancel is pressed (e.g. point queues)."""
        if listener not in self._cancel_listeners:
            self._cancel_listeners.append(listener)

    def remove_cancel_listener(self, listener: CancelListenerFn) -> None:
        """Stop calling *listener* on Cancel."""
        if listener in self._cancel_listeners:
            self._cancel_listeners.remove(listener)

    def request_cancel(self) -> None:
        """Signal the in-flight job to stop at the next cooperative checkpoint."""
        event = self._cancel_event
        if event is not None:
            event.set()
            self._job_cancel_requested = True
        self._refresh_status_bars()

    def cancel_all(self) -> None:
        """Cancel the running job and every registered long-running task (status-bar Cancel)."""
        self.request_cancel()
        for listener in list(self._cancel_listeners):
            try:
                listener()
            except Exception:
                _logger.exception("Cancel listener %r failed", listener)

    def report_point_queue(self, finished: int, total: int) -> None:
        """Show control-point queue progress; ``total <= 0`` hides it.

        Call on the GUI thread. A queue that starts while a job runs takes over
        the strip's text because it is the most recently started task.
        """
        if total <= 0:
            self.clear_point_queue()
            return
        total = int(total)
        finished = max(0, min(int(finished), total))
        if self._point_activity is None:
            self._activity_counter += 1
            self._point_activity = _Activity("", 0, 0, self._activity_counter)
        self._point_activity.text = format_point_queue_text(finished, total)
        self._point_activity.current = finished
        self._point_activity.total = total
        self._refresh_status_bars()

    def clear_point_queue(self) -> None:
        """Hide control-point queue progress (queue idle or cancelled)."""
        if self._point_activity is None:
            return
        self._point_activity = None
        self._refresh_status_bars()

    def _shown_activity(self) -> _Activity | None:
        """The most recently started active task, if any."""
        active = [a for a in (self._job_activity, self._point_activity) if a is not None]
        if not active:
            return None
        return max(active, key=lambda activity: activity.started)

    def _cancel_enabled(self) -> bool:
        """Cancel stays live while any task can still be cancelled."""
        if self._point_activity is not None:
            return True
        return self._job_activity is not None and not self._job_cancel_requested

    def _refresh_status_bars(self) -> None:
        """Push the shown activity (or hide the strip) to every registered status bar."""
        activity = self._shown_activity()
        cancel_enabled = self._cancel_enabled()
        with self._lock:
            bars = list(self._status_bars)
        for bar in bars:
            try:
                if activity is None:
                    bar.hide_activity()
                else:
                    bar.show_activity(activity.text, activity.current, activity.total, cancel_enabled)
            except RuntimeError:
                # The Qt widget was deleted with its window; stop updating it.
                self.unregister_status_bar(bar)

    def abandon(self) -> None:
        """Cancel the running job and ignore its result (e.g. a new STOS opened).

        Cooperative cancel is signaled, then this runner is marked idle so a
        later success/error callback from the abandoned generation is dropped.
        """
        event = self._cancel_event
        if event is not None:
            event.set()
        with self._lock:
            if not self._busy:
                return
            self._generation += 1
        self._finish_job()

    def submit(
            self,
            worker: WorkerFn[T],
            *,
            title: str,
            on_success: SuccessFn[T],
            on_error: ErrorFn | None = None,
            on_cancelled: CancelledFn | None = None,
            on_preview: PreviewFn | None = None,
    ) -> bool:
        """Start *worker* if idle. Returns False when a job is already running.

        *on_preview* is invoked on the GUI thread with optional per-pass
        payloads (grid refine delivers a transform snapshot). Later previews
        from the same job replace earlier ones that have not been applied yet.
        RefineTransform passes take seconds, so the GUI normally applies each
        snapshot before the next; coalescing only drops a preview when two
        arrive before the main thread runs.
        """
        with self._lock:
            if self._busy:
                return False
            self._busy = True
            self._generation += 1
            generation = self._generation
            cancel_event = threading.Event()
            self._cancel_event = cancel_event
            self._job_cancel_requested = False
            self._activity_counter += 1
            self._job_activity = _Activity(
                format_job_text(title, "", 0, 0), 0, 0, self._activity_counter)

        self._refresh_status_bars()
        for listener in list(self._busy_changed_listeners):
            listener(True)

        init_main_thread_dispatcher()
        preview_state: _PreviewState = {"seq": 0, "value": None}

        def progress_cb(
                current: int,
                total: int,
                label: str,
                preview: object | None = None,
        ) -> None:
            this_preview_seq: int | None = None
            if preview is not None:
                with self._lock:
                    next_seq = preview_state["seq"] + 1
                    preview_state["seq"] = next_seq
                    preview_state["value"] = preview
                    this_preview_seq = next_seq

            def _apply() -> None:
                if generation != self._generation:
                    return
                with self._lock:
                    still_busy = self._busy
                    latest_seq = preview_state["seq"]
                    preview_value = preview_state["value"]
                job_activity = self._job_activity
                if job_activity is not None:
                    job_activity.text = format_job_text(title, label, current, total)
                    job_activity.current = int(current)
                    job_activity.total = int(total)
                    self._refresh_status_bars()
                if (this_preview_seq is None
                        or on_preview is None
                        or not still_busy):
                    return
                if this_preview_seq != latest_seq:
                    return
                if preview_value is not None:
                    on_preview(preview_value)

            qt_post_to_main(_apply)

        def _run() -> T:
            # cProfile only on this worker thread — not the Qt UI message loop.
            from pyre.phase_profile import profile_registration_job

            with profile_registration_job(title):
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
        self._job_activity = None
        self._job_cancel_requested = False
        self._refresh_status_bars()
        for listener in list(self._busy_changed_listeners):
            listener(False)


_registration_job_runner: RegistrationJobRunner | None = None


def get_registration_job_runner() -> RegistrationJobRunner:
    """Return the process-wide registration job runner."""
    global _registration_job_runner
    if _registration_job_runner is None:
        _registration_job_runner = RegistrationJobRunner()
    return _registration_job_runner
