"""Stos Directory window — browse STOS group folders with Manual override support.

- Open Folder scans a STOS group directory and merges automatic ``*.stos`` files with
  overrides in ``Manual/`` (Nornir buildmanager layout).
- Refresh re-scans the current folder (disk changes) without reopening the dialog.
- Rows with a manual override show ``[Manual]`` and load the manual file on double-click
  (any table column) or Enter.
- Manual-only rows (manual present, automatic missing) use a darker yellow list color.
- **File Source** selector (Auto / Original / Manual) controls which variant loads on open and navigation.
- When the selected source cannot resolve a path, load falls back to Auto (manual preferred).
- Right-click offers Open automatic vs manual when both exist, and copy the resolved
  file path to the clipboard.
- Delete removes only the automatic ``*.stos`` file after Yes/Enter confirmation; never Manual/.
- Opening a folder named ``Manual`` prompts to use the parent STOS group instead; flat
  browse mode avoids nested ``Manual/Manual`` behavior.
- Page Up / Page Down navigate while this window has focus.
- Mouse back / forward buttons step the list when a folder is loaded (application-wide,
  same as ``+`` / ``-``).
- ``+`` / ``-`` / ``=`` step one transform when a folder is loaded (application-wide).
  On US QWERTY, unshifted ``=`` and ``-`` step down; ``Shift+=`` (``+``) steps up.
  ``Shift++`` / ``Shift+-`` step ten transforms (numpad; main keyboard ``Shift+-`` only).
- Transform table shows pair ZNCC when ``stos_quality.json`` has a fresh score; missing or
  stale scores are computed in the background. A histogram under the table marks the
  selected score. ZNCC text is tinted by empirical percentile in the folder (magenta low,
  soft white mid, green high); Manual gold styling is unchanged.
"""

from __future__ import annotations

import os
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass

from dependency_injector.wiring import inject, Provide
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTableWidget, QTableWidgetItem, QFileDialog,
    QMessageBox, QMenu, QHeaderView, QAbstractItemView,
)
from PyQt6.QtCore import Qt, QObject, QEvent, QTimer
from PyQt6.QtGui import QFontMetrics, QKeyEvent, QColor, QKeySequence, QShortcut, QMouseEvent, QGuiApplication

from nornir_imageregistration.stos_quality import (
    QualityCache,
    load_quality_cache,
    save_quality_cache,
    score_stos_into_cache,
)
from pyre.container import IContainer
from pyre.qt_eventmanager import init_main_thread_dispatcher, qt_post_to_main
from pyre.settings import AppSettings
from pyre.stos_manual_paths import (
    BrowseMode,
    StosBrowserRow,
    StosFileSource,
    is_manual_input_directory,
    parent_stos_group_folder,
    scan_stos_browser_rows,
)
from pyre.stos_quality_browser import (
    attach_quality_scores,
    format_quality_score,
    histogram_from_rows,
    quality_score_rgb,
    score_to_percentile,
    scores_from_rows,
)
from pyre.ui.widgets.stos_file_source_selector import StosFileSourceSelector
from pyre.ui.widgets.stos_quality_histogram import StosQualityHistogramWidget


@dataclass(frozen=True)
class _PendingStosLoad:
    """Queued browser navigation load request."""
    generation: int
    filepath: str
    index: int
    browser_basename: str | None


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


class StosBrowserListDeleteFilter(QObject):
    """Intercept Delete on the table widget so the main window need not hold focus."""

    _browser: StosFileBrowserWindow

    def __init__(self, browser: StosFileBrowserWindow):
        super().__init__(browser)
        self._browser = browser

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        del watched
        if event.type() != QEvent.Type.KeyPress:
            return False
        if not isinstance(event, QKeyEvent):
            return False
        if event.key() != Qt.Key.Key_Delete:
            return False
        self._browser._delete_automatic_at_index(self._browser._current_index)
        return True


_BROWSER_MIN_LAYOUT_WIDTH = 180
_BROWSER_LAYOUT_PADDING = 44  # list margins + scrollbar reserve


class StosFileBrowserWindow(QMainWindow):
    """Floating Stos Directory window listing transforms in a STOS group folder."""

    NAV_LOAD_DEBOUNCE_MS: int = 75

    _folder: str | None
    _browse_mode: BrowseMode
    _rows: list[StosBrowserRow]
    _current_index: int
    _settings: AppSettings
    _nav_shortcuts: list[QShortcut]
    _mouse_nav_filter: StosBrowserMouseNavigationFilter | None
    _list_delete_filter: StosBrowserListDeleteFilter | None
    _file_source_selector: StosFileSourceSelector
    _quality_histogram: StosQualityHistogramWidget
    _quality_cache: QualityCache
    _score_generation: int
    _scan_generation: int
    _last_completed_scan_generation: int
    _pending_rescan_basename: str | None
    _scan_future: Future | None
    _manual_override_color = QColor("#c9a227")
    _manual_only_color = QColor("#8b6914")
    _load_generation: int
    _pending_load: _PendingStosLoad | None
    _debounce_timer: QTimer
    _load_executor: ThreadPoolExecutor

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
        self.resize(380, 700)
        self._rows = []
        self._current_index = -1
        self._browse_mode = BrowseMode.stos_group
        self._folder = None
        self._nav_shortcuts = []
        self._mouse_nav_filter = None
        self._list_delete_filter = None
        self._load_generation = 0
        self._score_generation = 0
        self._scan_generation = 0
        self._last_completed_scan_generation = 0
        self._pending_rescan_basename = None
        self._scan_future = None
        self._quality_cache = QualityCache()
        self._pending_load = None
        self._load_executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="stos-nav-load")
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.timeout.connect(self._execute_pending_load)

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
        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.setToolTip("Re-scan the current folder for STOS files (F5)")
        self._refresh_btn.clicked.connect(self.rescan)
        self._refresh_btn.setEnabled(False)
        btn_row.addWidget(self._refresh_btn)
        layout.addLayout(btn_row)

        refresh_shortcut = QShortcut(QKeySequence(Qt.Key.Key_F5), self)
        refresh_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        refresh_shortcut.activated.connect(self.rescan)

        self._folder_label = QLabel("No folder selected")
        self._folder_label.setWordWrap(True)
        layout.addWidget(self._folder_label)

        self._file_source_selector = StosFileSourceSelector(self)
        self._file_source_selector.set_source(
            StosFileSource.from_settings_value(self._settings.stos.stos_file_source),
        )
        self._file_source_selector.source_changed.connect(self._on_file_source_changed)
        layout.addWidget(self._file_source_selector)

        self._list_widget = QTableWidget(0, 2)
        self._list_widget.setHorizontalHeaderLabels(['Transform', 'ZNCC'])
        self._list_widget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._list_widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._list_widget.verticalHeader().setVisible(False)
        header = self._list_widget.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        # Enter / platform "activate" (itemActivated) plus explicit double-click.
        # itemActivated alone is not reliable for QTableWidget double-click on Windows
        # when SH_ItemView_ActivateItemOnSingleClick is false.
        self._list_widget.itemActivated.connect(self._on_item_activated)
        self._list_widget.cellDoubleClicked.connect(self._on_cell_double_clicked)
        self._list_widget.itemSelectionChanged.connect(self._on_table_selection_changed)
        self._list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list_widget.customContextMenuRequested.connect(self._on_context_menu)
        self._list_delete_filter = StosBrowserListDeleteFilter(self)
        self._list_widget.installEventFilter(self._list_delete_filter)
        layout.addWidget(self._list_widget)

        self._quality_histogram = StosQualityHistogramWidget(self)
        layout.addWidget(self._quality_histogram)

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
        """Re-scan the current folder and refresh the list (preserves selection when possible)."""
        if not self._folder:
            return
        previous_basename: str | None = None
        if 0 <= self._current_index < len(self._rows):
            previous_basename = self._rows[self._current_index].basename
        self._queue_folder_scan(preserve_basename=previous_basename)

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
                    self._set_current_row(index)
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
        self._folder_label.setText(f"Scanning\u2026 {folder}")
        self._refresh_btn.setEnabled(True)
        self._file_source_selector.set_flat_manual_mode(mode == BrowseMode.flat_manual)
        self._rows = []
        self._current_index = -1
        self._list_widget.setRowCount(0)
        self._quality_histogram.set_histogram(histogram_from_rows([]), selected_score=None)
        self._update_source_selector_for_current_row()
        self._queue_folder_scan(preserve_basename=None)

    # ------------------------------------------------------------------
    # List population and loading
    # ------------------------------------------------------------------

    def minimum_layout_width(self) -> int:
        """Return the narrowest width that still shows row labels in automatic layouts."""
        metrics = QFontMetrics(self._list_widget.font())
        max_text = metrics.horizontalAdvance("Open Folder\u2026")
        for row in self._rows:
            label = row.basename
            if self._browse_mode == BrowseMode.stos_group and row.has_manual_override:
                label = f"{row.basename} [Manual]"
            max_text = max(max_text, metrics.horizontalAdvance(label))
        return max(_BROWSER_MIN_LAYOUT_WIDTH, max_text + _BROWSER_LAYOUT_PADDING + 64)

    def _set_current_row(self, index: int) -> None:
        """Select table row *index* (stand-in for ``QListWidget.setCurrentRow``)."""
        if index < 0 or index >= self._list_widget.rowCount():
            self._list_widget.clearSelection()
            return
        self._list_widget.setCurrentCell(index, 0)

    def _populate_list(self) -> None:
        """Fill the table from ``_rows`` (names and any scores already on the rows)."""
        self._populate_list_from_rows(self._rows, scores_ready=True)

    def _populate_list_from_rows(
            self,
            rows: list[StosBrowserRow],
            *,
            scores_ready: bool,
    ) -> None:
        """Build the transform table from *rows* (names always; scores or em dash)."""
        self._list_widget.setRowCount(0)
        self._list_widget.setRowCount(len(rows))
        scored_values = scores_from_rows(rows) if scores_ready else []
        for index, row in enumerate(rows):
            label = row.basename
            if self._browse_mode == BrowseMode.stos_group and row.has_manual_override:
                label = f"{row.basename} [Manual]"
            name_item = QTableWidgetItem(label)
            name_item.setFlags(
                Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            name_item.setToolTip(self._row_tooltip(row, scored_values if scores_ready else None))
            color = self._row_list_color(row)
            if color is not None:
                name_item.setForeground(color)
            display_score = row.quality_score if scores_ready else None
            score_item = QTableWidgetItem(format_quality_score(display_score))
            score_item.setFlags(
                Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            score_item.setTextAlignment(int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
            score_item.setToolTip(self._row_tooltip(row, scored_values if scores_ready else None))
            if color is not None:
                score_item.setForeground(color)
            elif display_score is not None:
                rgb = quality_score_rgb(float(display_score), scored_values)
                if rgb is not None:
                    score_item.setForeground(QColor.fromRgbF(rgb[0], rgb[1], rgb[2]))
            self._list_widget.setItem(index, 0, name_item)
            self._list_widget.setItem(index, 1, score_item)

        if 0 <= self._current_index < len(rows):
            self._set_current_row(self._current_index)
        self._update_source_selector_for_current_row()
        if scores_ready:
            self._refresh_quality_histogram()

    def _refresh_score_column_and_histogram(self) -> None:
        """Update ZNCC cells and histogram from ``_rows`` without rebuilding names."""
        scored_values = scores_from_rows(self._rows)
        for index, row in enumerate(self._rows):
            score_item = self._list_widget.item(index, 1)
            name_item = self._list_widget.item(index, 0)
            if score_item is None:
                continue
            score_item.setText(format_quality_score(row.quality_score))
            tip = self._row_tooltip(row, scored_values)
            score_item.setToolTip(tip)
            if name_item is not None:
                name_item.setToolTip(tip)
            color = self._row_list_color(row)
            if color is not None:
                score_item.setForeground(color)
            elif row.quality_score is not None:
                rgb = quality_score_rgb(float(row.quality_score), scored_values)
                if rgb is not None:
                    score_item.setForeground(QColor.fromRgbF(rgb[0], rgb[1], rgb[2]))
            else:
                score_item.setForeground(self._list_widget.palette().color(
                    self._list_widget.foregroundRole()))
        self._refresh_quality_histogram()

    def _queue_folder_scan(self, *, preserve_basename: str | None) -> None:
        """Scan the current folder and attach quality scores off the UI thread."""
        if not self._folder:
            return
        init_main_thread_dispatcher()
        self._scan_generation += 1
        self._score_generation += 1  # cancel in-flight ZNCC for a prior folder/scan
        generation = self._scan_generation
        self._pending_rescan_basename = preserve_basename
        folder = self._folder
        mode = self._browse_mode
        source = self._source_for_load()

        def _worker() -> None:
            if generation != self._scan_generation:
                return
            rows = scan_stos_browser_rows(folder, mode)
            if generation != self._scan_generation:
                return
            qt_post_to_main(
                lambda f=folder, r=rows, g=generation: self._on_scan_rows_ready(f, r, g))
            cache = load_quality_cache(folder)
            rows2, cache, stale = attach_quality_scores(folder, rows, source, cache=cache)
            if generation != self._scan_generation:
                return
            qt_post_to_main(
                lambda f=folder, r=rows2, c=cache, s=stale, g=generation:
                self._on_quality_attach_ready(f, r, c, s, g))

        self._scan_future = self._load_executor.submit(_worker)

    def _queue_quality_attach_only(self) -> None:
        """Re-attach cached scores for the current rows (e.g. Auto/Manual source change)."""
        if not self._folder or not self._rows:
            return
        init_main_thread_dispatcher()
        self._scan_generation += 1
        self._score_generation += 1
        generation = self._scan_generation
        folder = self._folder
        source = self._source_for_load()
        rows_snapshot = list(self._rows)

        def _worker() -> None:
            if generation != self._scan_generation:
                return
            cache = load_quality_cache(folder)
            rows2, cache, stale = attach_quality_scores(
                folder, rows_snapshot, source, cache=cache)
            if generation != self._scan_generation:
                return
            qt_post_to_main(
                lambda f=folder, r=rows2, c=cache, s=stale, g=generation:
                self._on_quality_attach_ready(f, r, c, s, g))

        self._scan_future = self._load_executor.submit(_worker)

    def _on_scan_rows_ready(
            self,
            folder: str,
            rows: list[StosBrowserRow],
            generation: int,
    ) -> None:
        """Apply basename rows after a background directory scan."""
        if generation != self._scan_generation or self._folder != folder:
            return
        self._rows = rows
        self._folder_label.setText(folder)
        self._populate_list_from_rows(rows, scores_ready=False)
        basename = self._pending_rescan_basename
        if basename is not None:
            for index, row in enumerate(rows):
                if row.basename == basename:
                    self._current_index = index
                    self._set_current_row(index)
                    break
            else:
                if rows:
                    self._current_index = min(max(0, self._current_index), len(rows) - 1)
                    self._set_current_row(self._current_index)
                else:
                    self._current_index = -1
            self._pending_rescan_basename = None
        self._update_source_selector_for_current_row()

    def _on_quality_attach_ready(
            self,
            folder: str,
            rows: list[StosBrowserRow],
            cache: QualityCache,
            stale: list[str],
            generation: int,
    ) -> None:
        """Apply attached scores after background cache/checksum work."""
        if generation != self._scan_generation or self._folder != folder:
            return
        self._rows = rows
        self._quality_cache = cache
        self._last_completed_scan_generation = generation
        if self._list_widget.rowCount() == len(rows):
            self._refresh_score_column_and_histogram()
        else:
            self._populate_list_from_rows(rows, scores_ready=True)
        if 0 <= self._current_index < len(rows):
            self._set_current_row(self._current_index)
        self._update_source_selector_for_current_row()
        if stale:
            self._queue_quality_scores(stale)

    def wait_for_scan_idle(self, timeout_s: float = 5.0) -> None:
        """Block until the outstanding folder scan/attach finishes (for tests)."""
        init_main_thread_dispatcher()
        future = self._scan_future
        if future is not None:
            future.result(timeout=timeout_s)
        app = QApplication.instance()
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if app is not None:
                app.processEvents()
            if self._last_completed_scan_generation == self._scan_generation:
                if app is not None:
                    app.processEvents()
                return
            time.sleep(0.01)
        raise TimeoutError("Stos Browser folder scan/attach did not complete")

    def _refresh_quality_histogram(self) -> None:
        selected = None
        row = self._current_row()
        if row is not None:
            selected = row.quality_score
        self._quality_histogram.set_histogram(
            histogram_from_rows(self._rows),
            selected_score=selected,
        )

    def _queue_quality_scores(self, paths: list[str]) -> None:
        """Compute missing/stale pair ZNCC scores in the background."""
        if not self._folder or not paths:
            return
        folder = self._folder
        self._score_generation += 1
        generation = self._score_generation
        unique_paths = list(dict.fromkeys(paths))
        source = self._source_for_load()
        rows_snapshot = [row.with_quality_score(None) for row in self._rows]

        def _worker() -> tuple[QualityCache, list[StosBrowserRow]]:
            cache = load_quality_cache(folder)
            for path in unique_paths:
                if generation != self._score_generation:
                    break
                if not os.path.isfile(path):
                    continue
                try:
                    cache, _entry, _computed = score_stos_into_cache(
                        folder, path, cache=cache, max_side=2048)
                except Exception as exc:
                    print(f"STOS quality score failed for {path}: {exc}")
            save_quality_cache(folder, cache)
            rows2, cache, _stale = attach_quality_scores(
                folder, rows_snapshot, source, cache=cache)
            return cache, rows2

        def _on_done(future: Future) -> None:
            try:
                cache, rows2 = future.result()
            except Exception as exc:
                print(f"STOS quality score worker failed: {exc}")
                return

            def _apply() -> None:
                if generation != self._score_generation or self._folder != folder:
                    return
                self._quality_cache = cache
                self._rows = rows2
                self._refresh_score_column_and_histogram()

            qt_post_to_main(_apply)

        future = self._load_executor.submit(_worker)
        future.add_done_callback(lambda f: _on_done(f))

    def _row_list_color(self, row: StosBrowserRow) -> QColor | None:
        """Return list foreground color for manual override / manual-only rows."""
        if self._browse_mode != BrowseMode.stos_group or not row.has_manual_override:
            return None
        if row.is_manual_only:
            return self._manual_only_color
        return self._manual_override_color

    def _current_row(self) -> StosBrowserRow | None:
        if self._current_index < 0 or self._current_index >= len(self._rows):
            return None
        return self._rows[self._current_index]

    def _row_has_auto(self, row: StosBrowserRow) -> bool:
        return row.auto_path is not None and os.path.isfile(row.auto_path)

    def _row_has_manual(self, row: StosBrowserRow) -> bool:
        return row.manual_path is not None and os.path.isfile(row.manual_path)

    def _row_can_delete_automatic(self, row: StosBrowserRow) -> bool:
        """True when Delete may remove the automatic STOS file for *row*."""
        if self._browse_mode == BrowseMode.flat_manual:
            return False
        return self._row_has_auto(row)

    def _update_source_selector_for_current_row(self) -> None:
        row = self._current_row()
        if row is None:
            self._file_source_selector.set_row_availability(has_auto=False, has_manual=False)
            return
        has_auto = self._row_has_auto(row)
        has_manual = self._row_has_manual(row)
        self._file_source_selector.set_row_availability(has_auto=has_auto, has_manual=has_manual)
        current = self._file_source_selector.source()
        if row.load_path_for_source(current) is None:
            fallback = StosFileSource.auto
            self._file_source_selector.set_source(fallback)
            self._settings.stos.stos_file_source = fallback.value

    def _on_table_selection_changed(self) -> None:
        index = self._list_widget.currentRow()
        if index < 0:
            self._current_index = -1
        else:
            self._current_index = index
        self._update_source_selector_for_current_row()
        self._refresh_quality_histogram()

    def _on_file_source_changed(self, source: StosFileSource) -> None:
        self._settings.stos.stos_file_source = source.value
        if self._folder:
            # Re-attach scores for the newly preferred Auto/Manual path off-thread.
            self._queue_quality_attach_only()
        if self._current_index >= 0:
            self._load_stos_at_index(self._current_index)

    def _source_for_load(self) -> StosFileSource:
        return StosFileSource.from_settings_value(self._settings.stos.stos_file_source)

    def _missing_source_message(self, source: StosFileSource, row: StosBrowserRow) -> str:
        label = {
            StosFileSource.original: "Original (automatic)",
            StosFileSource.manual: "Manual",
        }.get(source, source.value)
        return f"No {label} STOS file exists for {row.basename}."

    def _resolve_load_path_for_row(
            self, row: StosBrowserRow, source: StosFileSource) -> tuple[str | None, StosFileSource]:
        """Resolve a load path for *row*, falling back to Auto when *source* is missing."""
        load_path = row.load_path_for_source(source)
        if load_path is not None:
            return load_path, source
        if source != StosFileSource.auto:
            auto_path = row.load_path_for_source(StosFileSource.auto)
            if auto_path is not None:
                return auto_path, StosFileSource.auto
        return None, source

    @staticmethod
    def _row_tooltip(row: StosBrowserRow, scored_values: list[float] | None = None) -> str:
        auto = row.auto_path or "(none)"
        manual = row.manual_path or "(none)"
        tip = f"Automatic: {auto}\nManual: {manual}"
        if row.is_manual_only:
            tip += "\n(automatic missing)"
        if row.quality_score is not None:
            tip += f"\nPair ZNCC: {row.quality_score:.3f}"
            if scored_values is not None:
                percentile = score_to_percentile(float(row.quality_score), scored_values)
                if percentile is not None:
                    tip += f"\nPercentile: {100.0 * percentile:.0f}%"
        return tip

    def _on_item_activated(self, item: QTableWidgetItem) -> None:
        self._load_stos_at_index(item.row())

    def _on_cell_double_clicked(self, row: int, column: int) -> None:
        """Open the STOS for *row* on double-click (any column, including ZNCC)."""
        del column
        self._load_stos_at_index(row)

    def _on_context_menu(self, position) -> None:
        item = self._list_widget.itemAt(position)
        if item is None:
            return
        index = item.row()
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
                lambda: self._load_stos_path(row.auto_path, index, browser_basename=row.basename))

            manual_action = menu.addAction("Open Manual Override")
            manual_action.setEnabled(row.manual_path is not None)
            manual_action.triggered.connect(
                lambda: self._load_stos_path(row.manual_path, index, browser_basename=row.basename))

        menu.addSeparator()
        load_path, _ = self._resolve_load_path_for_row(row, self._source_for_load())
        copy_action = menu.addAction("Copy Full Path to Clipboard")
        copy_action.setEnabled(load_path is not None)
        copy_action.triggered.connect(lambda: self._copy_full_path_to_clipboard(row))

        menu.exec(self._list_widget.mapToGlobal(position))

    def _copy_full_path_to_clipboard(self, row: StosBrowserRow) -> None:
        """Copy the resolved STOS path for the current file-source preference."""
        source = self._source_for_load()
        load_path, used_source = self._resolve_load_path_for_row(row, source)
        if load_path is None:
            QMessageBox.information(self, "STOS not found", self._missing_source_message(source, row))
            return
        if used_source != source:
            self._file_source_selector.set_source(used_source)
            self._settings.stos.stos_file_source = used_source.value
        QGuiApplication.clipboard().setText(os.path.normpath(load_path))

    def _load_stos_at_index(self, index: int) -> None:
        if index < 0 or index >= len(self._rows):
            return
        row = self._rows[index]
        source = self._source_for_load()
        load_path, used_source = self._resolve_load_path_for_row(row, source)
        if load_path is None:
            QMessageBox.information(self, "STOS not found", self._missing_source_message(source, row))
            return
        if used_source != source:
            self._file_source_selector.set_source(used_source)
            self._settings.stos.stos_file_source = used_source.value
        self._load_stos_path(load_path, index, browser_basename=row.basename)

    def _load_stos_path(
            self,
            filepath: str | None,
            index: int,
            *,
            browser_basename: str | None = None,
    ) -> None:
        if not filepath:
            return
        self._load_generation += 1
        generation = self._load_generation
        self._current_index = index
        self._set_current_row(index)
        self.setWindowTitle(f"Stos Directory \u2014 {os.path.basename(filepath)}")
        self._pending_load = _PendingStosLoad(
            generation=generation,
            filepath=filepath,
            index=index,
            browser_basename=browser_basename,
        )
        self._debounce_timer.start(self.NAV_LOAD_DEBOUNCE_MS)

    def _execute_pending_load(self) -> None:
        """Start (or flush) the debounced STOS load for the latest pending request."""
        self._debounce_timer.stop()
        pending = self._pending_load
        if pending is None:
            return
        self._pending_load = None
        generation = pending.generation
        filepath = pending.filepath
        browser_basename = pending.browser_basename
        browser_folder = self._folder
        browser_flat_manual = self._browse_mode == BrowseMode.flat_manual

        def _worker() -> object:
            from pyre.ui.windows.stoswindow import StosWindow
            return StosWindow.load_stos_data(filepath)

        def _on_done(future: Future) -> None:
            def _apply() -> None:
                if generation != self._load_generation:
                    return
                try:
                    load_result = future.result()
                except Exception as exc:
                    print(f"Error loading stos file: {exc}")
                    return
                from pyre.ui.windows.stoswindow import StosWindow
                try:
                    StosWindow.apply_stos_load_result(
                        filepath,
                        load_result,
                        browser_folder=browser_folder,
                        browser_flat_manual=browser_flat_manual,
                        browser_basename=browser_basename,
                    )
                except Exception as exc:
                    print(f"Error applying stos file: {exc}")

            qt_post_to_main(_apply)

        future = self._load_executor.submit(_worker)
        future.add_done_callback(lambda f: _on_done(f))

    # ------------------------------------------------------------------
    # Delete automatic STOS
    # ------------------------------------------------------------------

    def _confirm_delete_automatic(self, row: StosBrowserRow) -> bool:
        """Ask the user to confirm deleting the automatic STOS file for *row*."""
        auto_path = row.auto_path or ""
        message = (
            f"Delete the automatic STOS file for {row.basename}?\n\n"
            f"{os.path.normpath(auto_path)}"
        )
        if self._row_has_manual(row):
            message += "\n\nThe manual override will not be deleted."
        reply = QMessageBox.question(
            self,
            "Delete automatic STOS",
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        return reply == QMessageBox.StandardButton.Yes

    def _delete_automatic_at_index(self, index: int) -> None:
        """Delete the automatic STOS file for the row at *index* after confirmation."""
        if index < 0 or index >= len(self._rows):
            return
        row = self._rows[index]
        if not self._row_can_delete_automatic(row):
            QMessageBox.information(
                self,
                "Nothing to delete",
                f"No automatic STOS file to delete for {row.basename}.",
            )
            return
        if not self._confirm_delete_automatic(row):
            return
        auto_path = row.auto_path
        assert auto_path is not None
        basename = row.basename
        try:
            os.remove(auto_path)
        except OSError as exc:
            QMessageBox.warning(
                self,
                "Delete failed",
                f"Could not delete automatic STOS file:\n\n{exc}",
            )
            return
        # Rescan off-thread; selection is restored by basename when names land.
        self._queue_folder_scan(preserve_basename=basename)

    # ------------------------------------------------------------------
    # Keyboard handling
    # ------------------------------------------------------------------

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_PageDown:
            self.navigate_next()
        elif event.key() == Qt.Key.Key_PageUp:
            self.navigate_previous()
        elif event.key() == Qt.Key.Key_Delete:
            self._delete_automatic_at_index(self._current_index)
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        """Drop the application event filter when the browser window closes."""
        self._debounce_timer.stop()
        self._pending_load = None
        self._load_generation += 1  # supersede any in-flight apply
        self._score_generation += 1
        self._remove_mouse_navigation_filter()
        self._load_executor.shutdown(wait=False, cancel_futures=True)
        super().closeEvent(event)
