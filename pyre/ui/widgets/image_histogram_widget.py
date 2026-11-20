"""Image intensity histogram with min/max markers and the gamma tone curve for contrast UI."""

from __future__ import annotations

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator
from PyQt6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget

from nornir_shared.histogram import Histogram
from pyre.ui.widgets.histogram_y_range import display_y_max, label_clipped_bins


# Points along the tone curve between Min and Max.
_CURVE_STEPS: int = 64


class ImageHistogramWidget(QWidget):
    """Render an intensity histogram with optional min/max cutoff lines and the gamma tone curve.

    As in Viking's contrast window, the curve shows how bright each intensity between Min and Max
    is drawn (black at the bottom, white at the top), and a dashed line marks the intensity drawn at
    mid grey, which is where the gamma puts the middle of the window.
    """

    _histogram: Histogram | None
    _min_marker: float | None
    _max_marker: float | None
    _gamma: float | None
    _min_line: Line2D | None
    _max_line: Line2D | None
    _curve_line: Line2D | None
    _mid_line: Line2D | None

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._histogram = None
        self._min_marker = None
        self._max_marker = None
        self._gamma = None
        self._min_line = None
        self._max_line = None
        self._curve_line = None
        self._mid_line = None
        self._figure = Figure(figsize=(4.0, 2.0), layout='constrained')
        self._axes = self._figure.add_subplot(111)
        # Tone curve axis: 0 (black) to 1 (white), drawn over the bars without its own ticks.
        self._curve_axes = self._axes.twinx()
        self._canvas = FigureCanvasQTAgg(self._figure)
        self._canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._canvas.setMinimumHeight(140)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._canvas)
        self._redraw()

    def set_histogram(
            self,
            histogram: Histogram | None,
            *,
            min_marker: float | None = None,
            max_marker: float | None = None,
            gamma: float | None = None,
    ) -> None:
        """Replace histogram data, optional level markers and the gamma of the tone curve."""
        self._histogram = histogram
        self._min_marker = min_marker
        self._max_marker = max_marker
        self._gamma = gamma
        self._redraw()

    def set_markers(self, min_marker: float | None, max_marker: float | None,
                    gamma: float | None = None) -> None:
        """Update only the min/max markers and the tone curve without rebuilding bars."""
        self._min_marker = min_marker
        self._max_marker = max_marker
        self._gamma = gamma
        if self._min_line is None or self._max_line is None:
            self._redraw()
            return
        if min_marker is not None:
            self._min_line.set_xdata([float(min_marker), float(min_marker)])
            self._min_line.set_visible(True)
        else:
            self._min_line.set_visible(False)
        if max_marker is not None:
            self._max_line.set_xdata([float(max_marker), float(max_marker)])
            self._max_line.set_visible(True)
        else:
            self._max_line.set_visible(False)
        self._update_tone_curve()
        self._canvas.draw_idle()

    def _update_tone_curve(self) -> None:
        """Place the gamma curve and mid-grey line for the current Min, Max and gamma; hide them without all three."""
        if self._curve_line is None or self._mid_line is None:
            return
        lo, hi, gamma = self._min_marker, self._max_marker, self._gamma
        if lo is None or hi is None or gamma is None or not hi > lo or not gamma > 0:
            self._curve_line.set_visible(False)
            self._mid_line.set_visible(False)
            return
        t = np.linspace(0.0, 1.0, _CURVE_STEPS + 1)
        self._curve_line.set_data(lo + t * (hi - lo), np.power(t, 1.0 / gamma))
        mid_x = lo + (hi - lo) * 0.5 ** gamma
        self._mid_line.set_xdata([mid_x, mid_x])
        self._curve_line.set_visible(True)
        self._mid_line.set_visible(True)

    def _redraw(self) -> None:
        """Draw bins and cutoff lines."""
        self._axes.clear()
        self._curve_axes.clear()
        self._min_line = None
        self._max_line = None
        self._curve_line = None
        self._mid_line = None
        hist = self._histogram
        y_max = 1.0
        if hist is None or hist.NumBins <= 0 or hist.NumSamples <= 0:
            self._axes.text(0.5, 0.5, 'No image', transform=self._axes.transAxes,
                            ha='center', va='center', fontsize=9, color='#666666')
            self._axes.set_xlim(0, 255)
        else:
            bin_edges = [
                float(hist.MinValue) + float(i) * float(hist.BinWidth)
                for i in range(hist.NumBins)
            ]
            widths = [float(hist.BinWidth)] * hist.NumBins
            self._axes.bar(bin_edges, hist.Bins, width=widths, align='edge',
                           color='#5b8def', edgecolor='none')
            y_max = display_y_max(hist.Bins)
            label_clipped_bins(self._axes, hist, y_max)
            self._axes.set_xlim(float(hist.MinValue), float(hist.MaxValue))
            self._axes.yaxis.set_major_locator(MaxNLocator(nbins=4, integer=True))
            self._axes.ticklabel_format(axis='y', style='plain', useOffset=False)
        self._axes.set_xlabel('Intensity')
        self._axes.set_ylabel('Count')
        self._axes.set_title('Histogram')
        # Always create line artists so later set_markers() can move them cheaply.
        min_x = 0.0 if self._min_marker is None else float(self._min_marker)
        max_x = 255.0 if self._max_marker is None else float(self._max_marker)
        self._min_line = self._axes.axvline(min_x, color='#27ae60', linewidth=1.4)
        self._max_line = self._axes.axvline(max_x, color='#c0392b', linewidth=1.4)
        self._min_line.set_visible(self._min_marker is not None)
        self._max_line.set_visible(self._max_marker is not None)
        self._axes.set_ylim(0, y_max)
        self._axes.margins(y=0)
        self._curve_axes.set_ylim(0.0, 1.02)
        self._curve_axes.set_xlim(self._axes.get_xlim())
        self._curve_axes.set_yticks([])
        (self._curve_line,) = self._curve_axes.plot([], [], color='#f39c12', linewidth=1.4)
        self._mid_line = self._axes.axvline(0.0, color='#7f8c8d', linewidth=1.0, linestyle='--')
        self._update_tone_curve()
        self._canvas.draw_idle()
