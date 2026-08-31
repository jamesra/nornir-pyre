"""Scrollable help dialog for Pyre mouse and keyboard controls."""

from __future__ import annotations

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import QDialog, QPlainTextEdit, QVBoxLayout

from pyre.resource_paths import (
    CONTROLS_HELP_ANCHOR,
    controls_help_anchor_index,
    controls_help_section,
)


class ControlsHelpDialog(QDialog):
    """Show bundled help text, scrolled to the mouse/keyboard controls section."""

    def __init__(self, parent, text: str, anchor: str = CONTROLS_HELP_ANCHOR) -> None:
        super().__init__(parent)
        self.setWindowTitle("Mouse and Keyboard Controls")
        self.resize(700, 500)
        self.setMinimumSize(480, 320)

        self._full_text = text
        self._anchor = anchor
        self._scrolled = False

        editor = QPlainTextEdit(self)
        editor.setReadOnly(True)
        editor.setPlainText(text)
        editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(editor)
        self._editor = editor

    def showEvent(self, event) -> None:  # noqa: N802 — Qt API
        super().showEvent(event)
        if not self._scrolled:
            self._scrolled = True
            QTimer.singleShot(0, self._scroll_to_controls)

    def _scroll_to_controls(self) -> None:
        document = self._editor.document()
        cursor = document.find(self._anchor)
        if not cursor.isNull():
            self._editor.setTextCursor(cursor)
            self._editor.ensureCursorVisible()
            return

        section = controls_help_section(self._full_text)
        if section is not None:
            self._editor.setPlainText(section)
            self._editor.moveCursor(QTextCursor.MoveOperation.Start)
            self._editor.ensureCursorVisible()
            return

        if controls_help_anchor_index(self._full_text, self._anchor) == 0:
            self._editor.moveCursor(QTextCursor.MoveOperation.Start)
            self._editor.ensureCursorVisible()
