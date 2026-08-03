"""Tests for deleting automatic STOS files from StosFileBrowserWindow."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication

from pyre.settings.app import AppSettings
from pyre.stos_manual_paths import BrowseMode, StosBrowserRow, StosFileSource, scan_stos_browser_rows
from pyre.ui.windows.stosfilebrowser import StosFileBrowserWindow


def _touch(path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("stub")


class TestStosFileBrowserDelete(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication(sys.argv)

    def _browser_for_folder(self, folder: str) -> StosFileBrowserWindow:
        browser = StosFileBrowserWindow(parent=None, settings=AppSettings())
        browser._folder = folder
        browser._browse_mode = BrowseMode.stos_group
        browser._rows = scan_stos_browser_rows(folder, BrowseMode.stos_group)
        browser._current_index = 0 if browser._rows else -1
        browser._populate_list()
        return browser

    def test_row_can_delete_automatic_guards(self) -> None:
        browser = StosFileBrowserWindow(parent=None, settings=AppSettings())
        browser._browse_mode = BrowseMode.stos_group
        with tempfile.TemporaryDirectory() as tmp:
            auto = os.path.join(tmp, "a.stos")
            manual = os.path.join(tmp, "Manual", "a.stos")
            _touch(auto)
            _touch(manual)
            auto_row = StosBrowserRow(basename="a.stos", auto_path=auto, manual_path=manual)
            self.assertTrue(browser._row_can_delete_automatic(auto_row))

            manual_only = StosBrowserRow(basename="a.stos", auto_path=None, manual_path=manual)
            self.assertFalse(browser._row_can_delete_automatic(manual_only))

            browser._browse_mode = BrowseMode.flat_manual
            self.assertFalse(browser._row_can_delete_automatic(auto_row))

    def test_delete_automatic_preserves_manual(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            auto = os.path.join(tmp, "10-11.stos")
            manual = os.path.join(tmp, "Manual", "10-11.stos")
            _touch(auto)
            _touch(manual)
            browser = self._browser_for_folder(tmp)
            browser._confirm_delete_automatic = MagicMock(return_value=True)

            browser._delete_automatic_at_index(0)

            self.assertFalse(os.path.isfile(auto))
            self.assertTrue(os.path.isfile(manual))
            self.assertEqual(len(browser._rows), 1)
            self.assertTrue(browser._rows[0].is_manual_only)
            item = browser._list_widget.item(0)
            self.assertIsNotNone(item)
            assert item is not None
            self.assertEqual(item.foreground().color(), QColor("#8b6914"))

    def test_delete_cancel_leaves_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            auto = os.path.join(tmp, "10-11.stos")
            _touch(auto)
            browser = self._browser_for_folder(tmp)
            browser._confirm_delete_automatic = MagicMock(return_value=False)

            browser._delete_automatic_at_index(0)

            self.assertTrue(os.path.isfile(auto))
            self.assertEqual(len(browser._rows), 1)
            self.assertIsNotNone(browser._rows[0].auto_path)

    def test_delete_without_auto_shows_info(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manual = os.path.join(tmp, "Manual", "10-11.stos")
            _touch(manual)
            browser = self._browser_for_folder(tmp)
            with patch.object(StosFileBrowserWindow, "_confirm_delete_automatic") as confirm:
                with patch("pyre.ui.windows.stosfilebrowser.QMessageBox.information") as info:
                    browser._delete_automatic_at_index(0)
            confirm.assert_not_called()
            info.assert_called_once()
            self.assertTrue(os.path.isfile(manual))

    def test_manual_only_row_uses_darker_color(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _touch(os.path.join(tmp, "Manual", "05-06.stos"))
            browser = self._browser_for_folder(tmp)
            item = browser._list_widget.item(0)
            self.assertIsNotNone(item)
            assert item is not None
            self.assertEqual(item.foreground().color(), browser._manual_only_color)

    def test_manual_override_row_uses_lighter_color(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _touch(os.path.join(tmp, "05-06.stos"))
            _touch(os.path.join(tmp, "Manual", "05-06.stos"))
            browser = self._browser_for_folder(tmp)
            item = browser._list_widget.item(0)
            self.assertIsNotNone(item)
            assert item is not None
            self.assertEqual(item.foreground().color(), browser._manual_override_color)

    def test_load_manual_only_with_auto_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manual = os.path.join(tmp, "Manual", "10-11.stos")
            _touch(manual)
            browser = self._browser_for_folder(tmp)
            browser._settings.stos.stos_file_source = StosFileSource.auto.value
            browser._file_source_selector.set_source(StosFileSource.auto)
            browser._debounce_timer.stop()
            browser._load_stos_at_index(0)
            pending = browser._pending_load
            self.assertIsNotNone(pending)
            assert pending is not None
            self.assertEqual(
                os.path.normcase(os.path.abspath(pending.filepath)),
                os.path.normcase(os.path.abspath(manual)),
            )

    def test_load_falls_back_from_original_to_auto_on_manual_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manual = os.path.join(tmp, "Manual", "10-11.stos")
            _touch(manual)
            browser = self._browser_for_folder(tmp)
            browser._settings.stos.stos_file_source = StosFileSource.original.value
            browser._file_source_selector.set_source(StosFileSource.original)
            browser._debounce_timer.stop()
            browser._load_stos_at_index(0)
            pending = browser._pending_load
            self.assertIsNotNone(pending)
            assert pending is not None
            self.assertEqual(
                os.path.normcase(os.path.abspath(pending.filepath)),
                os.path.normcase(os.path.abspath(manual)),
            )
            self.assertEqual(browser._settings.stos.stos_file_source, StosFileSource.auto.value)
            self.assertEqual(browser._file_source_selector.source(), StosFileSource.auto)


if __name__ == "__main__":
    unittest.main()
