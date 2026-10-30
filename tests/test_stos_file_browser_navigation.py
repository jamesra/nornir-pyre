"""Tests for StosFileBrowserWindow list navigation helpers."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock

from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QAbstractItemView, QApplication

from pyre.qt_eventmanager import init_main_thread_dispatcher
from pyre.settings.app import AppSettings
from pyre.stos_manual_paths import BrowseMode, StosBrowserRow
from pyre.ui.windows.stosfilebrowser import (
    StosBrowserMouseNavigationFilter,
    StosFileBrowserWindow,
)


def _make_rows(count: int) -> list[StosBrowserRow]:
    return [
        StosBrowserRow(
            basename=f"section_{i}.stos",
            auto_path=f"/tmp/section_{i}.stos",
            manual_path=None,
        )
        for i in range(count)
    ]


def _touch(path: str) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("stub")


class TestStosFileBrowserNavigation(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication(sys.argv)
        init_main_thread_dispatcher()

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

    def _mouse_button_press(self, button: Qt.MouseButton) -> QMouseEvent:
        return QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(0.0, 0.0),
            QPointF(0.0, 0.0),
            QPointF(0.0, 0.0),
            button,
            button,
            Qt.KeyboardModifier.NoModifier,
        )

    def test_mouse_back_forward_navigate_when_folder_loaded(self) -> None:
        browser = self._browser_with_rows(4, current_index=1)
        loaded: list[int] = []
        browser._load_stos_at_index = MagicMock(side_effect=lambda i: loaded.append(i))
        event_filter = StosBrowserMouseNavigationFilter(browser)

        handled_back = event_filter.eventFilter(browser, self._mouse_button_press(Qt.MouseButton.BackButton))
        handled_forward = event_filter.eventFilter(browser, self._mouse_button_press(Qt.MouseButton.ForwardButton))

        self.assertTrue(handled_back)
        self.assertTrue(handled_forward)
        self.assertEqual(loaded, [0, 2])

    def test_mouse_back_forward_ignored_without_folder(self) -> None:
        browser = self._browser_with_rows(4, current_index=1)
        browser._folder = None
        browser._load_stos_at_index = MagicMock()
        event_filter = StosBrowserMouseNavigationFilter(browser)

        handled = event_filter.eventFilter(browser, self._mouse_button_press(Qt.MouseButton.BackButton))

        self.assertFalse(handled)
        browser._load_stos_at_index.assert_not_called()

    def test_refresh_button_disabled_until_folder_applied(self) -> None:
        browser = StosFileBrowserWindow(parent=None, settings=AppSettings())
        self.assertFalse(browser._refresh_btn.isEnabled())
        with tempfile.TemporaryDirectory() as tmp:
            _touch(os.path.join(tmp, "a.stos"))
            browser._apply_folder(tmp, persist=False, confirm_manual=False)
            browser.wait_for_scan_idle()
            self.assertTrue(browser._refresh_btn.isEnabled())

    def test_rescan_picks_up_new_files_and_keeps_selection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first = os.path.join(tmp, "a.stos")
            second = os.path.join(tmp, "b.stos")
            _touch(first)
            browser = StosFileBrowserWindow(parent=None, settings=AppSettings())
            browser._apply_folder(tmp, persist=False, confirm_manual=False)
            browser.wait_for_scan_idle()
            self.assertEqual(len(browser._rows), 1)
            browser._current_index = 0
            browser._set_current_row(0)

            _touch(second)
            browser.rescan()
            browser.wait_for_scan_idle()

            self.assertEqual(len(browser._rows), 2)
            self.assertEqual(browser._rows[browser._current_index].basename, "a.stos")
            self.assertEqual(browser._list_widget.rowCount(), 2)

    def test_set_current_row_keeps_visible_item_in_place(self) -> None:
        """Selecting an already-visible row must not recenter the table."""
        browser = self._browser_with_rows(40, current_index=0)
        browser._populate_list()
        browser.resize(380, 280)
        browser.show()
        self._app.processEvents()
        table = browser._list_widget
        top_item = table.item(18, 0)
        self.assertIsNotNone(top_item)
        assert top_item is not None
        table.scrollToItem(top_item, QAbstractItemView.ScrollHint.PositionAtTop)
        self._app.processEvents()
        before = table.verticalScrollBar().value()
        self.assertGreater(before, 0)
        browser._set_current_row(18)
        self._app.processEvents()
        self.assertEqual(table.verticalScrollBar().value(), before)

    def test_load_stos_path_does_not_recenter_visible_row(self) -> None:
        """Double-click load must leave a visible row at the same scroll offset."""
        browser = self._browser_with_rows(40, current_index=0)
        browser._populate_list()
        browser.resize(380, 280)
        browser.show()
        self._app.processEvents()
        table = browser._list_widget
        top_item = table.item(18, 0)
        self.assertIsNotNone(top_item)
        assert top_item is not None
        table.scrollToItem(top_item, QAbstractItemView.ScrollHint.PositionAtTop)
        self._app.processEvents()
        before = table.verticalScrollBar().value()
        browser._load_stos_path("/tmp/section_18.stos", 18, browser_basename="section_18.stos")
        self._app.processEvents()
        self.assertEqual(table.verticalScrollBar().value(), before)


if __name__ == "__main__":
    unittest.main()
