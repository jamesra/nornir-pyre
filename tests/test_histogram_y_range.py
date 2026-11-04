"""Histogram plots ignore up to two spike bins when choosing the y-axis range.

A single saturated bin flattened the rest of the histogram (2026-11-03). The axis now
tops out at the tallest non-spike bin when the tallest one or two bins stand more than
2x above the next, and the clipped bars are labelled with their count.
"""
from __future__ import annotations

import unittest

from hypothesis import given, settings
from hypothesis import strategies as st
from nornir_shared.histogram import Histogram
from pyre.ui.widgets.histogram_y_range import (
    CLIPPED_HEADROOM,
    clipped_bin_indices,
    display_y_max,
)


class TestDisplayYMax(unittest.TestCase):

    def test_no_spike_uses_the_tallest_bin(self):
        self.assertEqual(display_y_max([10, 40, 30, 25]), 40.0)

    def test_one_spike_is_clipped(self):
        self.assertAlmostEqual(display_y_max([5000, 40, 30, 25]), 40.0 * CLIPPED_HEADROOM)

    def test_saturated_black_and_white_are_both_clipped(self):
        self.assertAlmostEqual(display_y_max([5000, 40, 30, 4800]), 40.0 * CLIPPED_HEADROOM)

    def test_exactly_twice_is_not_a_spike(self):
        self.assertEqual(display_y_max([80, 40, 30]), 80.0)

    def test_a_tall_peak_over_three_bins_is_not_clipped(self):
        self.assertEqual(display_y_max([10, 900, 950, 1000, 20]), 1000.0)

    def test_empty_and_single_bin(self):
        self.assertEqual(display_y_max([]), 1.0)
        self.assertEqual(display_y_max([0, 0]), 1.0)
        self.assertEqual(display_y_max([0, 7, 0]), 7.0)

    def test_clipped_bins_are_reported(self):
        bins = [5000, 40, 30, 4800]
        self.assertEqual(clipped_bin_indices(bins, display_y_max(bins)), [0, 3])

    @given(st.lists(st.integers(0, 10_000), min_size=1, max_size=64))
    @settings(max_examples=200, deadline=None)
    def test_at_most_two_bins_are_clipped_and_the_rest_fit(self, bins):
        y_max = display_y_max(bins)
        self.assertGreater(y_max, 0)
        self.assertLessEqual(len(clipped_bin_indices(bins, y_max)), 2)
        self.assertLessEqual(y_max, max(max(bins), 1) * CLIPPED_HEADROOM)


class TestWidgetsUseTheRobustRange(unittest.TestCase):

    def test_image_histogram_axis_ignores_a_saturated_bin(self):
        from PyQt6.QtWidgets import QApplication
        from pyre.ui.widgets.image_histogram_widget import ImageHistogramWidget

        _app = QApplication.instance() or QApplication([])
        widget = ImageHistogramWidget()
        hist = Histogram.FromArray([90_000] + [100 + i for i in range(254)] + [50], 0.0, 1.0)
        widget.set_histogram(hist)
        self.assertAlmostEqual(widget._axes.get_ylim()[1], 353 * CLIPPED_HEADROOM, places=3)
        self.assertEqual(len(widget._axes.texts), 1, "the clipped bar is labelled")


if __name__ == '__main__':
    unittest.main()
