import os

from dependency_injector.wiring import inject, Provide
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QListWidget, QListWidgetItem, QFileDialog
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeyEvent

from pyre.container import IContainer
from pyre.settings import AppSettings


class StosFileBrowserWindow(QMainWindow):
    """Floating window that lists .stos files in a folder and loads one on selection.

    - Open Folder button scans a directory for .stos files (non-recursive, sorted alphabetically).
    - Double-clicking or pressing Enter on a list item loads it into all three rendering windows.
    - Page Up / Page Down navigate one file at a time while the browser window has focus.
    - set_current_file() keeps the list selection in sync when a file is loaded externally.
    - The last opened folder is persisted in settings and restored on the next run.
    """

    _folder: str | None
    _stos_files: list[str]   # absolute paths, sorted alphabetically by basename
    _current_index: int       # index of the currently displayed file, -1 if none
    _settings: AppSettings

    @inject
    def __init__(self, parent=None,
                 settings: AppSettings = Provide[IContainer.settings]):
        super().__init__(parent)
        self._settings = settings
        self.setWindowTitle("Stos File Browser")
        self.resize(350, 600)
        self._stos_files = []
        self._current_index = -1

        # Restore the last folder used, if it still exists
        saved = settings.ui.stos_browser_folder
        self._folder = saved if (saved and os.path.isdir(saved)) else None

        self._setup_ui()

        if self._folder:
            self._folder_label.setText(self._folder)
            self._stos_files = self._scan_folder(self._folder)
            self._populate_list()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self):
        central = QWidget(self)
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        btn_row = QHBoxLayout()
        self._open_btn = QPushButton("Open Folder\u2026")
        self._open_btn.clicked.connect(self.open_folder)
        btn_row.addWidget(self._open_btn)
        layout.addLayout(btn_row)

        self._folder_label = QLabel("No folder selected")
        self._folder_label.setWordWrap(True)
        layout.addWidget(self._folder_label)

        self._list_widget = QListWidget()
        self._list_widget.itemActivated.connect(self._on_item_activated)
        layout.addWidget(self._list_widget)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def open_folder(self):
        """Show a folder-chooser dialog and populate the list with discovered .stos files."""
        start = self._folder or ""
        folder = QFileDialog.getExistingDirectory(self, "Choose Stos Folder", start)
        if not folder:
            return
        self._folder = folder
        self._settings.ui.stos_browser_folder = folder  # persisted by atexit SaveSettings
        self._folder_label.setText(folder)
        self._stos_files = self._scan_folder(folder)
        self._current_index = -1
        self._populate_list()

    def set_current_file(self, filepath: str):
        """Highlight the row matching *filepath*, if it is in the current folder listing.

        Call this after loading a .stos file externally (e.g. File > Open stos file) so the
        browser stays in sync without performing a redundant load.
        """
        norm = os.path.normcase(os.path.abspath(filepath))
        for i, p in enumerate(self._stos_files):
            if os.path.normcase(p) == norm:
                self._current_index = i
                self._list_widget.setCurrentRow(i)
                return

    def navigate_next(self):
        """Load the next .stos file in the list (Page Down)."""
        if not self._stos_files:
            return
        self._load_stos_at_index(min(self._current_index + 1, len(self._stos_files) - 1))

    def navigate_previous(self):
        """Load the previous .stos file in the list (Page Up)."""
        if not self._stos_files:
            return
        self._load_stos_at_index(max(self._current_index - 1, 0))

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _scan_folder(folder: str) -> list[str]:
        """Return absolute paths to all .stos files in *folder*, sorted by lowercase basename."""
        entries = [
            os.path.join(folder, f)
            for f in os.listdir(folder)
            if f.lower().endswith(".stos") and os.path.isfile(os.path.join(folder, f))
        ]
        entries.sort(key=lambda p: os.path.basename(p).lower())
        return entries

    def _populate_list(self):
        self._list_widget.clear()
        for path in self._stos_files:
            self._list_widget.addItem(os.path.basename(path))
        if self._current_index >= 0:
            self._list_widget.setCurrentRow(self._current_index)

    def _on_item_activated(self, item: QListWidgetItem):
        self._load_stos_at_index(self._list_widget.row(item))

    def _load_stos_at_index(self, index: int):
        """Load the .stos file at *index* and update the list selection and window title."""
        if index < 0 or index >= len(self._stos_files):
            return
        # Deferred import avoids a circular dependency at module load time.
        from pyre.ui.windows.stoswindow import StosWindow
        filepath = self._stos_files[index]
        StosWindow.loadStos(filepath)
        self._current_index = index
        self._list_widget.setCurrentRow(index)
        self.setWindowTitle(f"Stos Browser \u2014 {os.path.basename(filepath)}")

    # ------------------------------------------------------------------
    # Keyboard handling
    # ------------------------------------------------------------------

    def keyPressEvent(self, event: QKeyEvent):
        """Page Down / Page Up navigate one file at a time while this window has focus."""
        if event.key() == Qt.Key.Key_PageDown:
            self.navigate_next()
        elif event.key() == Qt.Key.Key_PageUp:
            self.navigate_previous()
        else:
            super().keyPressEvent(event)
