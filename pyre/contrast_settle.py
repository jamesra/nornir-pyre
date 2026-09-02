"""Debounce for contrast edits that trigger expensive republishing.

Contrast sliders write settings on every tick. Registration images are published
to shared memory as whole mosaics, so they must be rebuilt once the user stops
moving a slider rather than once per event.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from pyre.space import Space

_logger = logging.getLogger(__name__)

DEFAULT_SETTLE_MS: int = 300

SettleCallback = Callable[[Space], None]
ScheduleCallback = Callable[[int, Callable[[], None]], None]


def _qt_schedule(delay_ms: int, callback: Callable[[], None]) -> None:
    """Schedule *callback* on the Qt event loop after *delay_ms*."""
    from PyQt6.QtCore import QTimer

    QTimer.singleShot(delay_ms, callback)


def republish_alignment_images_for_space(space: Space) -> None:
    """Publish settled contrast for *space*; no-op when no STOS state is loaded."""
    import pyre.state

    config = pyre.state.get_current_stos_config()
    if config is None:
        return
    publish = getattr(config, "publish_alignment_images", None)
    if callable(publish):
        publish(space)


class ContrastSettleNotifier:
    """Calls back once per space after contrast writes stop for the settle window.

    ``schedule`` is injectable so tests can drive the timer without an event loop.
    """

    _on_settled: SettleCallback
    _delay_ms: int
    _schedule: ScheduleCallback
    _tokens: dict[Space, int]

    def __init__(
            self,
            on_settled: SettleCallback,
            *,
            delay_ms: int = DEFAULT_SETTLE_MS,
            schedule: ScheduleCallback | None = None,
    ) -> None:
        self._on_settled = on_settled
        self._delay_ms = int(delay_ms)
        self._schedule = schedule if schedule is not None else _qt_schedule
        self._tokens = {}

    def note_contrast_write(self, space: Space) -> None:
        """Restart the settle window for *space*; only the last write fires."""
        token = self._tokens.get(space, 0) + 1
        self._tokens[space] = token

        def _fire() -> None:
            if self._tokens.get(space) != token:
                return
            try:
                self._on_settled(space)
            except Exception:
                _logger.exception("Contrast settle handler failed for %s", space)

        self._schedule(self._delay_ms, _fire)

    def cancel(self, space: Space | None = None) -> None:
        """Drop pending settle callbacks for *space*, or for every space."""
        if space is None:
            self._tokens = {}
            return
        self._tokens.pop(space, None)
