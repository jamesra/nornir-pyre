"""Tests for window geometry persistence helpers."""

from __future__ import annotations

import sys
import unittest
from unittest.mock import MagicMock, patch

from PyQt6.QtCore import QRect
from PyQt6.QtWidgets import QApplication, QMainWindow

from pyre.settings.app import AppSettings, UISettings, WindowGeometry
from pyre.ui.window_geometry import (
    STOS_BROWSER_KEY,
    STOS_WINDOW_KEYS,
    apply_saved_browser_geometry,
    apply_saved_window_geometry,
    capture_window_geometry,
    is_geometry_valid,
)


def _screen(available: QRect) -> MagicMock:
    screen = MagicMock()
    screen.availableGeometry.return_value = available
    return screen


class TestIsGeometryValid(unittest.TestCase):
    def test_accepts_on_screen_rect(self) -> None:
        geom = WindowGeometry(x=100, y=100, width=800, height=600)
        screens = [_screen(QRect(0, 0, 1920, 1080))]
        self.assertTrue(is_geometry_valid(geom, screens))

    def test_rejects_fully_off_screen(self) -> None:
        geom = WindowGeometry(x=5000, y=5000, width=800, height=600)
        screens = [_screen(QRect(0, 0, 1920, 1080))]
        self.assertFalse(is_geometry_valid(geom, screens))

    def test_rejects_tiny_size(self) -> None:
        geom = WindowGeometry(x=0, y=0, width=50, height=50)
        screens = [_screen(QRect(0, 0, 1920, 1080))]
        self.assertFalse(is_geometry_valid(geom, screens))


class TestCaptureWindowGeometry(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication(sys.argv)

    def test_capture_writes_stos_window_keys(self) -> None:
        settings = AppSettings(ui=UISettings())
        windows: dict[str, QMainWindow] = {}
        for key in STOS_WINDOW_KEYS:
            win = QMainWindow()
            win.setGeometry(10 + len(windows) * 20, 20, 400, 300)
            win.show()
            windows[key] = win
        window_manager = MagicMock()
        window_manager.__contains__ = lambda _self, key: (
            (key.value if hasattr(key, "value") else key) in windows
        )
        window_manager.__getitem__ = lambda _self, key: windows[
            key.value if hasattr(key, "value") else key
        ]

        with patch("pyre.ui.windows.stoswindow.StosWindow._folder_browser", None):
            capture_window_geometry(settings, window_manager)

        self.assertEqual(set(settings.ui.window_geometry.keys()), set(STOS_WINDOW_KEYS))
        self.assertEqual(settings.ui.window_geometry["Source"].width, 400)


class TestApplySavedWindowGeometry(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication(sys.argv)

    def test_apply_returns_false_when_empty(self) -> None:
        settings = AppSettings(ui=UISettings())
        window_manager = MagicMock()
        self.assertFalse(apply_saved_window_geometry(settings, window_manager))

    @patch("PyQt6.QtGui.QGuiApplication")
    def test_apply_sets_geometry_and_always_shows_windows(self, mock_qgui: MagicMock) -> None:
        mock_qgui.screens.return_value = [_screen(QRect(0, 0, 1920, 1080))]
        saved = {
            key: WindowGeometry(x=100, y=100, width=800, height=600, visible=(key != "Source"))
            for key in STOS_WINDOW_KEYS
        }
        settings = AppSettings(ui=UISettings(window_geometry=saved))
        windows: dict[str, MagicMock] = {
            key: MagicMock(spec=QMainWindow) for key in STOS_WINDOW_KEYS
        }
        window_manager = MagicMock()
        window_manager.__getitem__ = lambda _self, key: windows[key]

        self.assertTrue(apply_saved_window_geometry(settings, window_manager))
        for key in STOS_WINDOW_KEYS:
            windows[key].setGeometry.assert_called_once_with(100, 100, 800, 600)
            windows[key].setVisible.assert_called_once_with(True)


class TestApplySavedBrowserGeometry(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication(sys.argv)

    @patch("PyQt6.QtGui.QGuiApplication")
    def test_apply_browser_geometry(self, mock_qgui: MagicMock) -> None:
        mock_qgui.screens.return_value = [_screen(QRect(0, 0, 1920, 1080))]
        geom = WindowGeometry(x=50, y=50, width=350, height=600, visible=True)
        settings = AppSettings(ui=UISettings(window_geometry={STOS_BROWSER_KEY: geom}))
        browser = MagicMock(spec=QMainWindow)

        self.assertTrue(apply_saved_browser_geometry(settings, browser))
        browser.setGeometry.assert_called_once_with(50, 50, 350, 600)
        browser.setVisible.assert_called_once_with(True)


class TestStartupBrowserPlacement(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication(sys.argv)

    @patch("pyre.ui.windows.stoswindow.apply_saved_browser_geometry", return_value=False)
    @patch("pyre.ui.windows.stosfilebrowser.StosFileBrowserWindow.has_cached_folder", return_value=True)
    def test_docks_browser_when_stos_geometry_restored_but_browser_not_saved(
            self, _has_cached: MagicMock, _apply_browser: MagicMock) -> None:
        from pyre.ui.windows.stoswindow import StosWindow

        settings = AppSettings(ui=UISettings(stos_browser_folder="/tmp/stos"))
        anchor = MagicMock()
        browser = MagicMock(spec=QMainWindow)
        StosWindow._folder_browser = browser
        try:
            StosWindow.open_folder_browser_if_cached_folder_exists(
                settings, anchor, geometry_restored=True)
        finally:
            StosWindow._folder_browser = None
        anchor._position_folder_browser_beside_composite.assert_called_once()


if __name__ == "__main__":
    unittest.main()
