"""Glyph paint interval while registration is running."""

from __future__ import annotations

import unittest

from pyre.ui.widgets.imagetransformviewpanel import (
    GLYPH_TIMER_IDLE_MS,
    GLYPH_TIMER_REGISTRATION_MS,
    glyph_timer_interval_ms,
)


class TestGlyphTimerInterval(unittest.TestCase):
    def test_idle_is_ten_hertz(self) -> None:
        self.assertEqual(
            glyph_timer_interval_ms(point_queue_busy=False, job_busy=False),
            GLYPH_TIMER_IDLE_MS)
        self.assertEqual(GLYPH_TIMER_IDLE_MS, 100)

    def test_registration_is_five_hertz_not_thirty(self) -> None:
        self.assertEqual(GLYPH_TIMER_REGISTRATION_MS, 200)
        self.assertEqual(
            glyph_timer_interval_ms(point_queue_busy=True, job_busy=False),
            GLYPH_TIMER_REGISTRATION_MS)
        self.assertEqual(
            glyph_timer_interval_ms(point_queue_busy=False, job_busy=True),
            GLYPH_TIMER_REGISTRATION_MS)
