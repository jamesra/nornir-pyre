"""What's New dialog for the curated Pyre user changelog."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)


class WhatsNewDialog(QDialog):
    """Show markdown release notes in a scrollable browser."""

    def __init__(
            self,
            parent: QWidget | None,
            markdown: str,
            *,
            title: str = "What's New in Pyre",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(640, 480)
        self.setMinimumSize(480, 320)

        heading = QLabel(title, self)
        font = heading.font()
        font.setPointSize(font.pointSize() + 2)
        font.setBold(True)
        heading.setFont(font)

        browser = QTextBrowser(self)
        browser.setOpenExternalLinks(True)
        browser.setMarkdown(markdown)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok, self)
        buttons.accepted.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.addWidget(heading)
        layout.addWidget(browser, stretch=1)
        layout.addWidget(buttons)
