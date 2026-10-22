"""Glyph paint interval while registration is running."""

from __future__ import annotations

import unittest

from pyre.ui.widgets.imagetransformviewpanel import (
    GLYPH_TIMER_IDLE_MS,
    GLYPH_TIMER_REGISTRATION_MS,
    glyph_timer_interval_ms,
    glyph_timer_needs_paint,
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


class TestGlyphTimerNeedsPaint(unittest.TestCase):
    """The glyph timer only repaints when a glyph on screen animates."""

    def test_idle_without_selection_does_not_paint(self) -> None:
        for blink_phase_changed in (False, True):
            self.assertFalse(glyph_timer_needs_paint(
                has_selection=False, blink_phase_changed=blink_phase_changed,
                point_queue_busy=False, job_busy=False))

    def test_selection_paints_only_when_blink_phase_flips(self) -> None:
        self.assertTrue(glyph_timer_needs_paint(
            has_selection=True, blink_phase_changed=True,
            point_queue_busy=False, job_busy=False))
        self.assertFalse(glyph_timer_needs_paint(
            has_selection=True, blink_phase_changed=False,
            point_queue_busy=False, job_busy=False))

    def test_busy_comet_and_jobs_paint_every_tick(self) -> None:
        for has_selection in (False, True):
            self.assertTrue(glyph_timer_needs_paint(
                has_selection=has_selection, blink_phase_changed=False,
                point_queue_busy=True, job_busy=False))
            self.assertTrue(glyph_timer_needs_paint(
                has_selection=has_selection, blink_phase_changed=False,
                point_queue_busy=False, job_busy=True))
