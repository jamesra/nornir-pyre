"""Linked QSlider + QDoubleSpinBox control pair."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QDoubleSpinBox, QHBoxLayout, QLabel, QSlider, QWidget


class LinkedSliderSpin(QWidget):
    """Horizontal label + slider + spinbox; slider and spin stay synchronized."""

    valueChanged = pyqtSignal(float)

    _slider: QSlider
    _spin: QDoubleSpinBox
    _updating: bool
    _slider_steps: int

    def __init__(
            self,
            label: str,
            *,
            minimum: float,
            maximum: float,
            value: float,
            decimals: int = 2,
            single_step: float = 0.1,
            parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._updating = False
        self._slider_steps = 1000
        self._min = float(minimum)
        self._max = float(maximum)

        self._slider = QSlider(Qt.Orientation.Horizontal, self)
        self._slider.setMinimum(0)
        self._slider.setMaximum(self._slider_steps)
        self._spin = QDoubleSpinBox(self)
        self._spin.setDecimals(decimals)
        self._spin.setSingleStep(single_step)
        self._spin.setRange(self._min, self._max)
        self._spin.setKeyboardTracking(False)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel(label, self))
        layout.addWidget(self._slider, stretch=1)
        layout.addWidget(self._spin)

        self._slider.valueChanged.connect(self._on_slider)
        self._spin.valueChanged.connect(self._on_spin)
        # Avoid noisy intermediate spin updates while the user types; slider remains live.
        self._spin.setKeyboardTracking(False)
        self.set_value(value)

    def value(self) -> float:
        """Return the current spinbox value."""
        return float(self._spin.value())

    def set_value(self, value: float) -> None:
        """Set both controls without emitting if unchanged."""
        value = float(np_clip(value, self._min, self._max))
        self._updating = True
        try:
            self._spin.setValue(value)
            self._slider.setValue(self._value_to_slider(value))
        finally:
            self._updating = False

    def set_range(self, minimum: float, maximum: float) -> None:
        """Update allowed numeric range for both controls."""
        self._min = float(minimum)
        self._max = float(maximum)
        self._spin.setRange(self._min, self._max)
        self.set_value(self.value())

    def _value_to_slider(self, value: float) -> int:
        span = max(self._max - self._min, 1e-9)
        t = (float(value) - self._min) / span
        return int(round(t * self._slider_steps))

    def _slider_to_value(self, slider_value: int) -> float:
        t = float(slider_value) / float(self._slider_steps)
        return self._min + t * (self._max - self._min)

    def _on_slider(self, slider_value: int) -> None:
        if self._updating:
            return
        value = self._slider_to_value(int(slider_value))
        self._updating = True
        try:
            self._spin.setValue(value)
        finally:
            self._updating = False
        self.valueChanged.emit(float(self._spin.value()))

    def _on_spin(self, value: float) -> None:
        if self._updating:
            return
        self._updating = True
        try:
            self._slider.setValue(self._value_to_slider(float(value)))
        finally:
            self._updating = False
        self.valueChanged.emit(float(value))


def np_clip(value: float, lo: float, hi: float) -> float:
    """Clamp *value* to [lo, hi] without importing numpy at module import time."""
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value
