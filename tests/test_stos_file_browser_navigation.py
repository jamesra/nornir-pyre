"""Tests for StosFileBrowserWindow list navigation helpers."""

from __future__ import annotations

import sys
import unittest
from unittest.mock import MagicMock

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from pyre.settings.app import AppSettings
from pyre.stos_manual_paths import BrowseMode, StosBrowserRow
from pyre.ui.windows.stosfilebrowser import StosFileBrowserWindow


def _make_rows(count: int) -> list[StosBrowserRow]:
    return [
        StosBrowserRow(
            basename=f"section_{i}.stos",
            auto_path=f"/tmp/section_{i}.stos",
            manual_path=None,
        )
        for i in range(count)
    ]


class TestStosFileBrowserNavigation(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication(sys.argv)

    def _browser_with_rows(self, count: int, current_index: int) -> StosFileBrowserWindow:
        browser = StosFileBrowserWindow(parent=None, settings=AppSettings())
        browser._folder = "/tmp/stos_group"
        browser._browse_mode = BrowseMode.stos_group
        browser._rows = _make_rows(count)
        browser._current_index = current_index
        return browser

    def test_navigate_by_delta_steps_and_clamps(self) -> None:
        browser = self._browser_with_rows(5, current_index=2)
        loaded: list[int] = []
        browser._load_stos_at_index = MagicMock(side_effect=lambda i: loaded.append(i))

        browser.navigate_by_delta(+1)
        browser.navigate_by_delta(-1)
        browser.navigate_by_delta(-10)
        browser.navigate_by_delta(+10)

        self.assertEqual(loaded, [3, 1, 0, 4])

    def test_navigate_by_delta_noop_without_folder(self) -> None:
        browser = self._browser_with_rows(3, current_index=1)
        browser._folder = None
        browser._load_stos_at_index = MagicMock()

        browser.navigate_by_delta(+1)

        browser._load_stos_at_index.assert_not_called()

    def test_navigate_by_delta_noop_without_rows(self) -> None:
        browser = self._browser_with_rows(0, current_index=-1)
        browser._load_stos_at_index = MagicMock()

        browser.navigate_by_delta(+1)

        browser._load_stos_at_index.assert_not_called()

    def test_navigation_shortcuts_registered(self) -> None:
        browser = StosFileBrowserWindow(parent=None, settings=AppSettings())
        self.assertEqual(len(browser._nav_shortcuts), 5)
        for shortcut in browser._nav_shortcuts:
            self.assertEqual(shortcut.context(), Qt.ShortcutContext.ApplicationShortcut)


if __name__ == "__main__":
    unittest.main()
