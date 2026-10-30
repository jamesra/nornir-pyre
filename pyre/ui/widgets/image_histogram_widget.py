"""Image intensity histogram with min/max markers for contrast UI."""

from __future__ import annotations

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator
from PyQt6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget

from nornir_shared.histogram import Histogram


class ImageHistogramWidget(QWidget):
    """Render an intensity histogram with optional min/max cutoff lines."""

    _histogram: Histogram | None
    _min_marker: float | None
    _max_marker: float | None
    _min_line: Line2D | None
    _max_line: Line2D | None

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._histogram = None
        self._min_marker = None
        self._max_marker = None
        self._min_line = None
        self._max_line = None
        self._figure = Figure(figsize=(4.0, 2.0), layout='constrained')
        self._axes = self._figure.add_subplot(111)
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
    ) -> None:
        """Replace histogram data and optional level markers."""
        self._histogram = histogram
        self._min_marker = min_marker
        self._max_marker = max_marker
        self._redraw()

    def set_markers(self, min_marker: float | None, max_marker: float | None) -> None:
        """Update only the vertical min/max markers without rebuilding bars."""
        self._min_marker = min_marker
        self._max_marker = max_marker
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
        self._canvas.draw_idle()

    def _redraw(self) -> None:
        """Draw bins and cutoff lines."""
        self._axes.clear()
        self._min_line = None
        self._max_line = None
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
            y_max = max((float(count) for count in hist.Bins), default=1.0)
            if y_max <= 0:
                y_max = 1.0
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
        self._canvas.draw_idle()
