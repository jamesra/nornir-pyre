"""Tests for STOS browser file-source loading behavior."""

from __future__ import annotations

import os
import sys
import tempfile
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
    ) -> StosFileBrowserWindow:
        settings = AppSettings(stos=StosSettings(stos_file_source=source.value))
        browser = StosFileBrowserWindow(parent=None, settings=settings)
        browser._folder = "/tmp/stos_group"
        browser._browse_mode = BrowseMode.stos_group
        browser._rows = [
            StosBrowserRow(
                basename="10-11.stos",
                auto_path=auto_path,
                manual_path=manual_path,
            )
        ]
        browser._current_index = 0
        browser._file_source_selector.set_source(source)
        browser._debounce_timer.stop()
        return browser

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


if __name__ == "__main__":
    unittest.main()
