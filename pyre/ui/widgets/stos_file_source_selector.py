"""File Source selector for the Stos Directory browser."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QWidget

from pyre.stos_manual_paths import StosFileSource

_SOURCE_LABELS: dict[StosFileSource, str] = {
    StosFileSource.auto: "Auto",
    StosFileSource.original: "Original",
    StosFileSource.manual: "Manual",
}


class StosFileSourceSelector(QWidget):
    """Combo-box control for Auto / Original / Manual STOS file source."""

    source_changed = pyqtSignal(StosFileSource)

    _combo: QComboBox
    _flat_manual_mode: bool
    _suppress_signal: bool

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._flat_manual_mode = False
        self._suppress_signal = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel("File Source:"))

        self._combo = QComboBox(self)
        for source in (StosFileSource.auto, StosFileSource.original, StosFileSource.manual):
            self._combo.addItem(_SOURCE_LABELS[source], source.value)
        self._combo.currentIndexChanged.connect(self._on_combo_changed)
        layout.addWidget(self._combo, 1)

    def source(self) -> StosFileSource:
        """Return the currently selected file source."""
        value = self._combo.currentData()
        return StosFileSource.from_settings_value(value if isinstance(value, str) else None)

    def set_source(self, source: StosFileSource, *, emit_signal: bool = False) -> None:
        """Select *source* without emitting unless *emit_signal* is True."""
        index = self._combo.findData(source.value)
        if index < 0:
            index = 0
        self._suppress_signal = not emit_signal
        try:
            self._combo.setCurrentIndex(index)
        finally:
            self._suppress_signal = False

    def set_flat_manual_mode(self, flat_manual: bool) -> None:
        """Hide Original when browsing a flat Manual folder."""
        self._flat_manual_mode = flat_manual
        original_index = self._combo.findData(StosFileSource.original.value)
        if original_index >= 0:
            self._combo.model().item(original_index).setEnabled(not flat_manual)

    def set_row_availability(self, *, has_auto: bool, has_manual: bool) -> None:
        """Enable or disable Original/Manual based on the current list row."""
        auto_index = self._combo.findData(StosFileSource.auto.value)
        original_index = self._combo.findData(StosFileSource.original.value)
        manual_index = self._combo.findData(StosFileSource.manual.value)
        if auto_index >= 0:
            self._combo.model().item(auto_index).setEnabled(True)
        if original_index >= 0:
            enabled = has_auto and not self._flat_manual_mode
            self._combo.model().item(original_index).setEnabled(enabled)
        if manual_index >= 0:
            self._combo.model().item(manual_index).setEnabled(has_manual)

    def _on_combo_changed(self, _index: int) -> None:
        if self._suppress_signal:
            return
        self.source_changed.emit(self.source())
