"""Y-axis range for histogram plots that ignores a few spike bins.

One saturated bin (black or white pixels, failed registrations scoring 0) can be many
times taller than the rest and flatten everything else into the x-axis.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

MAX_SPIKE_BINS = 2  # black and white saturation together; more is a real peak, not spikes
SPIKE_RATIO = 2.0
CLIPPED_HEADROOM = 1.1


def display_y_max(bins: Sequence[float]) -> float:
    """Top of the y-axis: the tallest bin, or the tallest non-spike bin when up to
    ``MAX_SPIKE_BINS`` bins stand more than ``SPIKE_RATIO`` times above the rest.

    Counts are sorted tallest first and the deepest such gap among the top
    ``MAX_SPIKE_BINS`` decides the cut, so two similar spikes (e.g. 0 and 255) are both
    clipped. Clipped axes get a little headroom so the spikes visibly run off the top.
    """
    heights = sorted((float(b) for b in bins if b > 0), reverse=True)
    if not heights:
        return 1.0
    cut = 0
    for k in range(min(MAX_SPIKE_BINS, len(heights) - 1)):
        if heights[k] > SPIKE_RATIO * heights[k + 1]:
            cut = k + 1
    if cut == 0:
        return heights[0]
    return heights[cut] * CLIPPED_HEADROOM


def clipped_bin_indices(bins: Sequence[float], y_max: float) -> list[int]:
    """Bins taller than the axis, which the plot labels with their count."""
    return [i for i, b in enumerate(bins) if float(b) > y_max]


def label_clipped_bins(axes: Any, hist: Any, y_max: float) -> None:
    """Write the count at the top of each bar that runs off the axis."""
    for i in clipped_bin_indices(hist.Bins, y_max):
        x = float(hist.MinValue) + (i + 0.5) * float(hist.BinWidth)
        axes.annotate(f'{int(hist.Bins[i]):,}', xy=(x, y_max), xytext=(0, -2),
                      textcoords='offset points', ha='center', va='top',
                      fontsize=7, color='#333333', rotation=90)
