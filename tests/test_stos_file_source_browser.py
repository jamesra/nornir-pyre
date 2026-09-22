"""Tests for STOS browser file-source loading behavior."""

from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from PyQt6.QtWidgets import QApplication

from pyre.settings.app import AppSettings, StosSettings
from pyre.stos_manual_paths import BrowseMode, StosBrowserRow, StosFileSource
from pyre.ui.windows.stosfilebrowser import StosFileBrowserWindow


class TestStosBrowserFileSource(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication(sys.argv)

    def _browser_with_row(
            self,
            *,
            auto_path: str | None,
            manual_path: str | None,
            source: StosFileSource,
            input_path: str | None = None,
            folder: str | None = None,
            basename: str = "10-11.stos",
    ) -> StosFileBrowserWindow:
        settings = AppSettings(stos=StosSettings(stos_file_source=source.value))
        browser = StosFileBrowserWindow(parent=None, settings=settings)
        browser._scan_generation += 1
        browser._score_generation += 1
        browser._debounce_timer.stop()
        browser._pending_load = None
        browser._folder = folder if folder is not None else "/tmp/stos_group"
        browser._browse_mode = BrowseMode.stos_group
        browser._rows = [
            StosBrowserRow(
                basename=basename,
                auto_path=auto_path,
                manual_path=manual_path,
                input_path=input_path,
            )
        ]
        browser._current_index = 0
        browser._file_source_selector.set_source(source)
        browser._debounce_timer.stop()
        browser._pending_load = None
        self.addCleanup(self._shutdown_browser, browser)
        return browser

    def _shutdown_browser(self, browser: StosFileBrowserWindow) -> None:
        browser._debounce_timer.stop()
        browser._pending_load = None
        browser._scan_generation += 1
        browser._score_generation += 1
        browser.close()

    def test_load_at_index_uses_manual_when_source_manual(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            auto = os.path.join(tmp, "10-11.stos")
            manual = os.path.join(tmp, "Manual", "10-11.stos")
            os.makedirs(os.path.dirname(manual), exist_ok=True)
            open(auto, "w", encoding="utf-8").close()
            open(manual, "w", encoding="utf-8").close()
            browser = self._browser_with_row(
                auto_path=auto,
                manual_path=manual,
                source=StosFileSource.manual,
            )
            browser._load_stos_at_index(0)
            pending = browser._pending_load
            self.assertIsNotNone(pending)
            assert pending is not None
            self.assertEqual(pending.filepath, manual)
            self.assertEqual(pending.browser_basename, "10-11.stos")
            self.assertEqual(pending.index, 0)

    def test_load_at_index_uses_auto_when_source_original(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            auto = os.path.join(tmp, "10-11.stos")
            manual = os.path.join(tmp, "Manual", "10-11.stos")
            os.makedirs(os.path.dirname(manual), exist_ok=True)
            open(auto, "w", encoding="utf-8").close()
            open(manual, "w", encoding="utf-8").close()
            browser = self._browser_with_row(
                auto_path=auto,
                manual_path=manual,
                source=StosFileSource.original,
            )
            browser._load_stos_at_index(0)
            pending = browser._pending_load
            self.assertIsNotNone(pending)
            assert pending is not None
            self.assertEqual(pending.filepath, auto)

    def test_missing_manual_falls_back_to_auto_instead_of_message(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            auto = os.path.join(tmp, "10-11.stos")
            open(auto, "w", encoding="utf-8").close()
            browser = self._browser_with_row(
                auto_path=auto,
                manual_path=None,
                source=StosFileSource.manual,
            )
            with patch("pyre.ui.windows.stosfilebrowser.QMessageBox.information") as mock_box:
                browser._load_stos_at_index(0)
            mock_box.assert_not_called()
            pending = browser._pending_load
            self.assertIsNotNone(pending)
            assert pending is not None
            self.assertEqual(pending.filepath, auto)
            self.assertEqual(browser._settings.stos.stos_file_source, StosFileSource.auto.value)

    def test_copy_full_path_uses_resolved_path_for_file_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            auto = os.path.join(tmp, "10-11.stos")
            manual = os.path.join(tmp, "Manual", "10-11.stos")
            os.makedirs(os.path.dirname(manual), exist_ok=True)
            open(auto, "w", encoding="utf-8").close()
            open(manual, "w", encoding="utf-8").close()
            browser = self._browser_with_row(
                auto_path=auto,
                manual_path=manual,
                source=StosFileSource.manual,
            )
            browser._copy_full_path_to_clipboard(browser._rows[0])
            self.assertEqual(
                QApplication.clipboard().text(),
                os.path.normpath(manual),
            )

    def test_copy_full_path_falls_back_to_auto_when_manual_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            auto = os.path.join(tmp, "10-11.stos")
            open(auto, "w", encoding="utf-8").close()
            browser = self._browser_with_row(
                auto_path=auto,
                manual_path=None,
                source=StosFileSource.manual,
            )
            with patch("pyre.ui.windows.stosfilebrowser.QMessageBox.information") as mock_box:
                browser._copy_full_path_to_clipboard(browser._rows[0])
            mock_box.assert_not_called()
            self.assertEqual(
                QApplication.clipboard().text(),
                os.path.normpath(auto),
            )
            self.assertEqual(browser._settings.stos.stos_file_source, StosFileSource.auto.value)

    def test_cell_double_clicked_loads_stos(self) -> None:
        """Double-click on either table column must queue a STOS load."""
        with tempfile.TemporaryDirectory() as tmp:
            auto = os.path.join(tmp, "10-11.stos")
            open(auto, "w", encoding="utf-8").close()
            browser = self._browser_with_row(
                auto_path=auto,
                manual_path=None,
                source=StosFileSource.auto,
            )
            browser._populate_list()
            browser._on_cell_double_clicked(0, 1)  # Quality column
            pending = browser._pending_load
            self.assertIsNotNone(pending)
            assert pending is not None
            self.assertEqual(pending.filepath, auto)
            self.assertEqual(pending.index, 0)

    def test_load_at_index_uses_automatic_when_source_input(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            auto = os.path.join(tmp, "10-11.stos")
            input_stos = os.path.join(tmp, "Automatic", "10-11.stos")
            os.makedirs(os.path.dirname(input_stos), exist_ok=True)
            open(auto, "w", encoding="utf-8").close()
            open(input_stos, "w", encoding="utf-8").close()
            browser = self._browser_with_row(
                auto_path=auto,
                manual_path=None,
                input_path=input_stos,
                source=StosFileSource.input,
            )
            browser._load_stos_at_index(0)
            pending = browser._pending_load
            self.assertIsNotNone(pending)
            assert pending is not None
            self.assertEqual(pending.filepath, input_stos)

    def test_open_input_transform_loads_automatic_not_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            auto = os.path.join(tmp, "10-11.stos")
            input_stos = os.path.join(tmp, "Automatic", "10-11.stos")
            os.makedirs(os.path.dirname(input_stos), exist_ok=True)
            open(auto, "w", encoding="utf-8").close()
            open(input_stos, "w", encoding="utf-8").close()
            browser = self._browser_with_row(
                auto_path=auto,
                manual_path=None,
                input_path=input_stos,
                source=StosFileSource.original,
            )
            browser._load_stos_path(browser._rows[0].input_path, 0, browser_basename="10-11.stos")
            pending = browser._pending_load
            self.assertIsNotNone(pending)
            assert pending is not None
            self.assertEqual(pending.filepath, input_stos)
            self.assertNotEqual(pending.filepath, auto)

    def test_missing_input_falls_back_to_auto(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            auto = os.path.join(tmp, "10-11.stos")
            open(auto, "w", encoding="utf-8").close()
            browser = self._browser_with_row(
                auto_path=auto,
                manual_path=None,
                input_path=None,
                source=StosFileSource.input,
            )
            with patch("pyre.ui.windows.stosfilebrowser.QMessageBox.information") as mock_box:
                browser._load_stos_at_index(0)
            mock_box.assert_not_called()
            pending = browser._pending_load
            self.assertIsNotNone(pending)
            assert pending is not None
            self.assertEqual(pending.filepath, auto)
            self.assertEqual(browser._settings.stos.stos_file_source, StosFileSource.auto.value)

    def test_item_activated_loads_stos(self) -> None:
        """Enter / platform activate on a table item must queue a STOS load."""
        with tempfile.TemporaryDirectory() as tmp:
            auto = os.path.join(tmp, "10-11.stos")
            open(auto, "w", encoding="utf-8").close()
            browser = self._browser_with_row(
                auto_path=auto,
                manual_path=None,
                source=StosFileSource.auto,
            )
            browser._populate_list()
            item = browser._list_widget.item(0, 0)
            self.assertIsNotNone(item)
            assert item is not None
            browser._on_item_activated(item)
            pending = browser._pending_load
            self.assertIsNotNone(pending)
            assert pending is not None
            self.assertEqual(pending.filepath, auto)


    def _source_item_enabled(self, browser: StosFileBrowserWindow, source: StosFileSource) -> bool:
        combo = browser._file_source_selector._combo
        index = combo.findData(source.value)
        model = combo.model()
        item = model.item(index) if hasattr(model, "item") else None
        self.assertIsNotNone(item)
        assert item is not None
        return item.isEnabled()

    def test_double_click_loads_output_created_after_scan(self) -> None:
        """Group-root output written after the last scan must load instead of a missing-file dialog."""
        with tempfile.TemporaryDirectory() as tmp:
            basename = "1133-1130.stos"
            input_stos = os.path.join(tmp, "Automatic", basename)
            output = os.path.join(tmp, basename)
            os.makedirs(os.path.dirname(input_stos), exist_ok=True)
            open(input_stos, "w", encoding="utf-8").close()
            browser = self._browser_with_row(
                auto_path=None,
                manual_path=None,
                input_path=input_stos,
                source=StosFileSource.original,
                folder=tmp,
                basename=basename,
            )
            browser._refresh_row_from_disk(0)
            browser._update_source_selector_for_current_row()
            self.assertFalse(self._source_item_enabled(browser, StosFileSource.original))
            self.assertIsNone(browser._pending_load)
            open(output, "w", encoding="utf-8").close()
            with patch("pyre.ui.windows.stosfilebrowser.QMessageBox.information") as mock_box:
                browser._on_cell_double_clicked(0, 0)
            mock_box.assert_not_called()
            pending = browser._pending_load
            self.assertIsNotNone(pending)
            assert pending is not None
            self.assertEqual(pending.filepath, output)
            self.assertTrue(self._source_item_enabled(browser, StosFileSource.original))
            self.assertTrue(self._source_item_enabled(browser, StosFileSource.input))

    def test_selection_updates_file_source_items_without_loading(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            basename = "1133-1130.stos"
            input_stos = os.path.join(tmp, "Automatic", basename)
            output = os.path.join(tmp, basename)
            os.makedirs(os.path.dirname(input_stos), exist_ok=True)
            open(input_stos, "w", encoding="utf-8").close()
            browser = self._browser_with_row(
                auto_path=None,
                manual_path=None,
                input_path=input_stos,
                source=StosFileSource.input,
                folder=tmp,
                basename=basename,
            )
            browser._refresh_row_from_disk(0)
            browser._update_source_selector_for_current_row()
            self.assertFalse(self._source_item_enabled(browser, StosFileSource.original))
            open(output, "w", encoding="utf-8").close()
            with patch("pyre.ui.windows.stosfilebrowser.QMessageBox.information") as mock_box:
                browser._current_index = 0
                browser._refresh_row_from_disk(0)
                browser._update_source_selector_for_current_row()
            mock_box.assert_not_called()
            self.assertIsNone(browser._pending_load)
            self.assertTrue(self._source_item_enabled(browser, StosFileSource.original))
            self.assertTrue(self._source_item_enabled(browser, StosFileSource.input))

    def test_double_click_missing_original_reports_expected_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            basename = "1133-1130.stos"
            input_stos = os.path.join(tmp, "Automatic", basename)
            os.makedirs(os.path.dirname(input_stos), exist_ok=True)
            open(input_stos, "w", encoding="utf-8").close()
            browser = self._browser_with_row(
                auto_path=None,
                manual_path=None,
                input_path=input_stos,
                source=StosFileSource.original,
                folder=tmp,
                basename=basename,
            )
            with patch("pyre.ui.windows.stosfilebrowser.QMessageBox.information") as mock_box:
                browser._on_cell_double_clicked(0, 0)
            mock_box.assert_called_once()
            message = mock_box.call_args.args[2]
            self.assertIn(basename, message)
            self.assertIn(os.path.normpath(os.path.join(tmp, basename)), message)
            self.assertIsNone(browser._pending_load)

    def test_modified_column_uses_time_for_today_and_iso_date_otherwise(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            today_path = os.path.join(tmp, "today.stos")
            old_path = os.path.join(tmp, "old.stos")
            open(today_path, "w", encoding="utf-8").close()
            open(old_path, "w", encoding="utf-8").close()
            older = time.time() - 2 * 86400
            os.utime(old_path, (older, older))
            settings = AppSettings(stos=StosSettings(stos_file_source=StosFileSource.original.value))
            browser = StosFileBrowserWindow(parent=None, settings=settings)
            self.addCleanup(self._shutdown_browser, browser)
            browser._scan_generation += 1
            browser._score_generation += 1
            browser._debounce_timer.stop()
            browser._pending_load = None
            browser._folder = tmp
            browser._browse_mode = BrowseMode.stos_group
            browser._rows = [
                StosBrowserRow(basename="today.stos", auto_path=today_path, manual_path=None),
                StosBrowserRow(basename="old.stos", auto_path=old_path, manual_path=None),
            ]
            browser._populate_list_from_rows(browser._rows, scores_ready=False)
            self.assertEqual(
                browser._list_widget.horizontalHeaderItem(2).text(),
                "Modified",
            )
            self.assertRegex(browser._list_widget.item(0, 2).text(), r"^\d{2}:\d{2}$")
            self.assertRegex(browser._list_widget.item(1, 2).text(), r"^\d{2}-\d{2}-\d{2}$")
            self.assertIn("Modified:", browser._list_widget.item(0, 2).toolTip())

    def test_modified_column_follows_file_source_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            auto = os.path.join(tmp, "10-11.stos")
            manual = os.path.join(tmp, "Manual", "10-11.stos")
            os.makedirs(os.path.dirname(manual), exist_ok=True)
            open(auto, "w", encoding="utf-8").close()
            open(manual, "w", encoding="utf-8").close()
            older = time.time() - 2 * 86400
            os.utime(manual, (older, older))
            browser = self._browser_with_row(
                auto_path=auto,
                manual_path=manual,
                source=StosFileSource.original,
                folder=tmp,
            )
            browser._populate_list_from_rows(browser._rows, scores_ready=False)
            browser._debounce_timer.stop()
            browser._pending_load = None
            self.assertRegex(browser._list_widget.item(0, 2).text(), r"^\d{2}:\d{2}$")
            browser._file_source_selector.set_source(
                StosFileSource.manual, emit_signal=True)
            browser._debounce_timer.stop()
            browser._pending_load = None
            self.assertRegex(browser._list_widget.item(0, 2).text(), r"^\d{2}-\d{2}-\d{2}$")


if __name__ == "__main__":
    unittest.main()
