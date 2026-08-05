"""Qt widget: STOS quality histogram with optional selected-score marker."""

from __future__ import annotations

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PyQt6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget

from nornir_shared.histogram import Histogram

from nornir_imageregistration.stos_quality import (
    DEFAULT_HIST_MAX,
    DEFAULT_HIST_MIN,
    build_quality_histogram,
)


class StosQualityHistogramWidget(QWidget):
    """Render a :class:`Histogram` of pair ZNCC scores with a selection marker."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._histogram: Histogram = build_quality_histogram([])
        self._selected_score: float | None = None
        self._figure = Figure(figsize=(3.2, 1.6), layout='constrained')
        self._canvas = FigureCanvasQTAgg(self._figure)
        self._canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._canvas.setMinimumHeight(120)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._canvas)
        self._redraw()

    def set_histogram(
            self,
            histogram: Histogram | None,
            *,
            selected_score: float | None = None,
    ) -> None:
        """Replace the model histogram and optional selected-score marker."""
        if histogram is None:
            self._histogram = build_quality_histogram([])
        else:
            self._histogram = histogram
        self._selected_score = selected_score
        self._redraw()

    def set_selected_score(self, score: float | None) -> None:
        """Update only the vertical marker for the selected row."""
        self._selected_score = score
        self._redraw()

    def _redraw(self) -> None:
        """Draw ``Histogram.Bins`` and an optional selected-score line on the canvas."""
        self._figure.clear()
        axes = self._figure.add_subplot(111)
        hist = self._histogram
        bin_edges = [
            float(hist.MinValue) + float(i) * float(hist.BinWidth)
            for i in range(hist.NumBins)
        ]
        widths = [float(hist.BinWidth)] * hist.NumBins if hist.NumBins else []
        if hist.NumBins and hist.NumSamples > 0:
            axes.bar(bin_edges, hist.Bins, width=widths, align='edge', color='#5b8def', edgecolor='none')
            y_max = max(hist.Bins) if hist.Bins else 1
        else:
            y_max = 1
            axes.text(0.5, 0.5, 'No scores yet', transform=axes.transAxes,
                      ha='center', va='center', fontsize=9, color='#666666')
        if self._selected_score is not None:
            axes.axvline(float(self._selected_score), color='#c0392b', linewidth=1.5)
            axes.annotate(
                f'{self._selected_score:.3f}',
                xy=(float(self._selected_score), y_max * 0.9),
                xytext=(4, 0),
                textcoords='offset points',
                fontsize=8,
                color='#c0392b',
            )
        axes.set_xlim(DEFAULT_HIST_MIN, DEFAULT_HIST_MAX)
        axes.set_ylim(0, max(1, y_max) * 1.15)
        axes.set_xlabel('ZNCC')
        axes.set_ylabel('Count')
        axes.set_title('Pair ZNCC')
        self._canvas.draw_idle()
