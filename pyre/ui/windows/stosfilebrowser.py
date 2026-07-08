"""Stos Directory window — browse STOS group folders with Manual override support.

Future (not implemented): sortable columns for filename and overall quality score.

- Open Folder scans a STOS group directory and merges automatic ``*.stos`` files with
  overrides in ``Manual/`` (Nornir buildmanager layout).
- Rows with a manual override show ``[Manual]`` and load the manual file on double-click.
- Right-click offers Open automatic vs manual when both exist.
- Opening a folder named ``Manual`` prompts to use the parent STOS group instead; flat
  browse mode avoids nested ``Manual/Manual`` behavior.
- Page Up / Page Down navigate while this window has focus.
- Mouse back / forward buttons step the list when a folder is loaded (application-wide,
  same as ``+`` / ``-``).
- ``+`` / ``-`` / ``=`` step one transform when a folder is loaded (application-wide).
  On US QWERTY, unshifted ``=`` and ``-`` step down; ``Shift+=`` (``+``) steps up.
  ``Shift++`` / ``Shift+-`` step ten transforms (numpad; main keyboard ``Shift+-`` only).
"""

from __future__ import annotations

import os

from dependency_injector.wiring import inject, Provide
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QListWidget, QListWidgetItem, QFileDialog,
    QMessageBox, QMenu,
)
from PyQt6.QtCore import Qt, QObject, QEvent
from PyQt6.QtGui import QKeyEvent, QColor, QKeySequence, QShortcut, QMouseEvent

from pyre.container import IContainer
from pyre.settings import AppSettings
from pyre.stos_manual_paths import (
    BrowseMode,
    StosBrowserRow,
    is_manual_input_directory,
    parent_stos_group_folder,
    scan_stos_browser_rows,
)


class StosBrowserMouseNavigationFilter(QObject):
    """Application-wide filter: mouse back/forward step the STOS list when a folder is loaded."""

    _browser: StosFileBrowserWindow

    def __init__(self, browser: StosFileBrowserWindow):
        super().__init__(browser)
        self._browser = browser

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        del watched
        if event.type() != QEvent.Type.MouseButtonPress:
            return False
        if not isinstance(event, QMouseEvent):
            return False
        if not self._browser.list_navigation_available():
            return False
        if event.button() == Qt.MouseButton.BackButton:
            self._browser.navigate_previous()
            return True
        if event.button() == Qt.MouseButton.ForwardButton:
            self._browser.navigate_next()
            return True
        return False


class StosFileBrowserWindow(QMainWindow):
    """Floating Stos Directory window listing transforms in a STOS group folder."""

    _folder: str | None
    _browse_mode: BrowseMode
    _rows: list[StosBrowserRow]
    _current_index: int
    _settings: AppSettings
    _nav_shortcuts: list[QShortcut]
    _mouse_nav_filter: StosBrowserMouseNavigationFilter | None
    _manual_override_color = QColor("#c9a227")

    @staticmethod
    def has_cached_folder(settings: AppSettings) -> bool:
        """True when settings remember a browser folder that still exists on disk."""
        saved = settings.ui.stos_browser_folder
        return bool(saved and os.path.isdir(saved))

    @staticmethod
    def cached_folder_path(settings: AppSettings) -> str | None:
        """Return the saved browser folder when it exists, else None."""
        saved = settings.ui.stos_browser_folder
        return saved if (saved and os.path.isdir(saved)) else None

    @inject
    def __init__(self, parent=None,
                 settings: AppSettings = Provide[IContainer.settings]):
        super().__init__(parent)
        self._settings = settings
        self.setWindowTitle("Stos Directory")
        self.resize(350, 600)
        self._rows = []
        self._current_index = -1
        self._browse_mode = BrowseMode.stos_group
        self._folder = None
        self._nav_shortcuts = []
        self._mouse_nav_filter = None

        self._setup_ui()
        self._install_mouse_navigation_filter()

        cached = StosFileBrowserWindow.cached_folder_path(settings)
        if cached:
            self._apply_folder(cached, persist=False, confirm_manual=False)

        if self._folder:
            last_loaded = settings.stos.stos_fullpath
            if last_loaded:
                self.set_current_file(last_loaded)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
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
        self._list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list_widget.customContextMenuRequested.connect(self._on_context_menu)
        layout.addWidget(self._list_widget)

        self._setup_navigation_shortcuts()

    def _setup_navigation_shortcuts(self) -> None:
        """Register application-wide shortcuts for stepping through the transform list."""
        self._add_nav_shortcut("+", -1)
        self._add_nav_shortcut("-", +1)
        self._add_nav_shortcut("=", +1)
        self._add_nav_shortcut("Shift++", -10)
        self._add_nav_shortcut("Shift+-", +10)

    def _add_nav_shortcut(self, sequence: str, delta: int) -> None:
        """Bind *sequence* to move the current selection by *delta* list rows."""
        shortcut = QShortcut(QKeySequence(sequence), self)
        shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        shortcut.activated.connect(lambda d=delta: self.navigate_by_delta(d))
        self._nav_shortcuts.append(shortcut)

    def _install_mouse_navigation_filter(self) -> None:
        """Listen for mouse back/forward anywhere in the app while a folder is loaded."""
        from PyQt6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is None:
            return
        self._mouse_nav_filter = StosBrowserMouseNavigationFilter(self)
        app.installEventFilter(self._mouse_nav_filter)

    def _remove_mouse_navigation_filter(self) -> None:
        from PyQt6.QtWidgets import QApplication

        if self._mouse_nav_filter is None:
            return
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self._mouse_nav_filter)
        self._mouse_nav_filter = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list_navigation_available(self) -> bool:
        """True when the browser has a folder scan with at least one transform row."""
        return bool(self._folder and self._rows)

    @property
    def browse_mode(self) -> BrowseMode:
        return self._browse_mode

    def rescan(self) -> None:
        """Refresh the listing after an external save."""
        if not self._folder:
            return
        self._rows = scan_stos_browser_rows(self._folder, self._browse_mode)
        self._populate_list()

    def open_folder(self) -> None:
        """Show a folder chooser and populate the list with discovered transforms."""
        start = self._folder or ""
        folder = QFileDialog.getExistingDirectory(self, "Choose Stos Folder", start)
        if not folder:
            return
        self._apply_folder(folder, persist=True, confirm_manual=True)

    def set_current_file(self, filepath: str) -> None:
        """Highlight the row matching *filepath* without loading."""
        norm = os.path.normcase(os.path.abspath(filepath))
        for index, row in enumerate(self._rows):
            for candidate in (row.auto_path, row.manual_path, row.default_load_path):
                if candidate and os.path.normcase(os.path.abspath(candidate)) == norm:
                    self._current_index = index
                    self._list_widget.setCurrentRow(index)
                    return

    def navigate_by_delta(self, delta: int) -> None:
        """Load the transform *delta* rows from the current selection (clamped to list bounds)."""
        if not self.list_navigation_available():
            return
        target = max(0, min(self._current_index + delta, len(self._rows) - 1))
        self._load_stos_at_index(target)

    def navigate_next(self) -> None:
        """Load the next transform (Page Down)."""
        self.navigate_by_delta(+1)

    def navigate_previous(self) -> None:
        """Load the previous transform (Page Up)."""
        self.navigate_by_delta(-1)

    # ------------------------------------------------------------------
    # Folder selection and Manual guard
    # ------------------------------------------------------------------

    def _confirm_manual_folder_choice(self, manual_folder: str) -> str | BrowseMode | None:
        """Prompt when the user selected a Manual directory. Returns parent path, flat mode, or None."""
        parent = parent_stos_group_folder(manual_folder)
        if parent is None:
            return BrowseMode.flat_manual

        parent_name = os.path.basename(parent)
        message = (
            "It appears you are opening the folder of manual overrides. "
            f"Are you sure you didn't mean {parent_name}?"
        )
        box = QMessageBox(self)
        box.setWindowTitle("Open STOS folder")
        box.setText(message)
        open_parent = box.addButton(
            f"Open parent folder ({parent_name})",
            QMessageBox.ButtonRole.AcceptRole,
        )
        open_manual = box.addButton(
            "Open Manual folder anyway",
            QMessageBox.ButtonRole.ActionRole,
        )
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(open_parent)
        box.exec()

        clicked = box.clickedButton()
        if clicked is open_parent:
            return parent
        if clicked is open_manual:
            return BrowseMode.flat_manual
        return None

    def _resolve_folder_and_mode(
            self, folder: str, *, confirm_manual: bool) -> tuple[str, BrowseMode] | None:
        if not is_manual_input_directory(folder):
            return folder, BrowseMode.stos_group

        if not confirm_manual:
            parent = parent_stos_group_folder(folder)
            if parent is not None:
                return parent, BrowseMode.stos_group
            return folder, BrowseMode.flat_manual

        choice = self._confirm_manual_folder_choice(folder)
        if choice is None:
            return None
        if choice == BrowseMode.flat_manual:
            return folder, BrowseMode.flat_manual
        return str(choice), BrowseMode.stos_group

    def _apply_folder(self, folder: str, *, persist: bool, confirm_manual: bool) -> None:
        resolved = self._resolve_folder_and_mode(folder, confirm_manual=confirm_manual)
        if resolved is None:
            return
        folder, mode = resolved
        self._folder = folder
        self._browse_mode = mode
        if persist:
            self._settings.ui.stos_browser_folder = folder
        self._folder_label.setText(folder)
        self._rows = scan_stos_browser_rows(folder, self._browse_mode)
        self._current_index = -1
        self._populate_list()

    # ------------------------------------------------------------------
    # List population and loading
    # ------------------------------------------------------------------

    def _populate_list(self) -> None:
        self._list_widget.clear()
        for row in self._rows:
            label = row.basename
            if self._browse_mode == BrowseMode.stos_group and row.has_manual_override:
                label = f"{row.basename} [Manual]"
            item = QListWidgetItem(label)
            item.setToolTip(self._row_tooltip(row))
            if self._browse_mode == BrowseMode.stos_group and row.has_manual_override:
                item.setForeground(self._manual_override_color)
            self._list_widget.addItem(item)
        if 0 <= self._current_index < len(self._rows):
            self._list_widget.setCurrentRow(self._current_index)

    @staticmethod
    def _row_tooltip(row: StosBrowserRow) -> str:
        auto = row.auto_path or "(none)"
        manual = row.manual_path or "(none)"
        return f"Automatic: {auto}\nManual: {manual}"

    def _on_item_activated(self, item: QListWidgetItem) -> None:
        self._load_stos_at_index(self._list_widget.row(item))

    def _on_context_menu(self, position) -> None:
        item = self._list_widget.itemAt(position)
        if item is None:
            return
        index = self._list_widget.row(item)
        if index < 0 or index >= len(self._rows):
            return
        row = self._rows[index]
        menu = QMenu(self)
        open_action = menu.addAction("Open")
        open_action.triggered.connect(lambda: self._load_stos_at_index(index))

        if self._browse_mode == BrowseMode.stos_group:
            auto_action = menu.addAction("Open Automatic Transform")
            auto_action.setEnabled(row.auto_path is not None)
            auto_action.triggered.connect(
                lambda: self._load_stos_path(row.auto_path, index))

            manual_action = menu.addAction("Open Manual Override")
            manual_action.setEnabled(row.manual_path is not None)
            manual_action.triggered.connect(
                lambda: self._load_stos_path(row.manual_path, index))

        menu.exec(self._list_widget.mapToGlobal(position))

    def _load_stos_at_index(self, index: int) -> None:
        if index < 0 or index >= len(self._rows):
            return
        row = self._rows[index]
        load_path = row.default_load_path
        if load_path is None:
            return
        self._load_stos_path(load_path, index)

    def _load_stos_path(self, filepath: str | None, index: int) -> None:
        if not filepath:
            return
        from pyre.ui.windows.stoswindow import StosWindow
        StosWindow.loadStos(
            filepath,
            browser_folder=self._folder,
            browser_flat_manual=(self._browse_mode == BrowseMode.flat_manual),
        )
        self._current_index = index
        self._list_widget.setCurrentRow(index)
        self.setWindowTitle(f"Stos Directory \u2014 {os.path.basename(filepath)}")

    # ------------------------------------------------------------------
    # Keyboard handling
    # ------------------------------------------------------------------

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_PageDown:
            self.navigate_next()
        elif event.key() == Qt.Key.Key_PageUp:
            self.navigate_previous()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        """Drop the application event filter when the browser window closes."""
        self._remove_mouse_navigation_filter()
        super().closeEvent(event)
