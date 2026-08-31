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
    apply_frame_geometry_to_widget,
    apply_saved_browser_geometry,
    apply_saved_window_geometry,
    capture_window_geometry,
    clamp_frame_geometry,
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

    def test_rejects_title_bar_above_work_area(self) -> None:
        geom = WindowGeometry(x=339, y=-30, width=1260, height=1077)
        screens = [_screen(QRect(0, 0, 1920, 1080))]
        self.assertFalse(is_geometry_valid(geom, screens))

    def test_rejects_tiny_size(self) -> None:
        geom = WindowGeometry(x=0, y=0, width=50, height=50)
        screens = [_screen(QRect(0, 0, 1920, 1080))]
        self.assertFalse(is_geometry_valid(geom, screens))


class TestClampFrameGeometry(unittest.TestCase):
    def test_clamps_negative_y_to_work_area_top(self) -> None:
        geom = WindowGeometry(x=100, y=-30, width=800, height=600)
        screens = [_screen(QRect(0, 0, 1920, 1080))]
        clamped = clamp_frame_geometry(geom, screens)
        self.assertEqual(clamped.y, 0)


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
    def test_apply_sets_frame_geometry_and_always_shows_windows(self, mock_qgui: MagicMock) -> None:
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
            windows[key].setGeometry.assert_called_once()
            windows[key].setVisible.assert_called_once_with(True)

    @patch("PyQt6.QtGui.QGuiApplication")
    def test_apply_returns_false_when_title_bar_off_screen(self, mock_qgui: MagicMock) -> None:
        mock_qgui.screens.return_value = [_screen(QRect(0, 0, 1920, 1080))]
        saved = {
            key: WindowGeometry(x=100, y=-30, width=800, height=600)
            for key in STOS_WINDOW_KEYS
        }
        settings = AppSettings(ui=UISettings(window_geometry=saved))
        window_manager = MagicMock()
        self.assertFalse(apply_saved_window_geometry(settings, window_manager))


class TestApplyFrameGeometryToWidget(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication(sys.argv)

    def test_clamps_negative_y_on_apply(self) -> None:
        widget = QMainWindow()
        widget.show()
        screens = [_screen(QRect(0, 0, 1920, 1080))]
        apply_frame_geometry_to_widget(widget, 100, -30, 800, 600, screens=screens)
        QApplication.processEvents()
        frame = widget.frameGeometry()
        self.assertGreaterEqual(frame.y(), 0)


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
        browser.setGeometry.assert_called_once()
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
        anchor._layout_browser_left_of_composite.assert_called_once()

    @patch("pyre.ui.windows.stoswindow.StosWindow.apply_single_monitor_composite_layout")
    @patch("pyre.ui.windows.stoswindow.apply_saved_browser_geometry", return_value=False)
    @patch("pyre.ui.windows.stosfilebrowser.StosFileBrowserWindow.has_cached_folder", return_value=True)
    @patch("PyQt6.QtGui.QGuiApplication")
    def test_single_monitor_layout_when_stos_not_restored(
            self,
            mock_qgui: MagicMock,
            _has_cached: MagicMock,
            _apply_browser: MagicMock,
            mock_layout: MagicMock) -> None:
        from pyre.ui.windows.stoswindow import StosWindow

        mock_qgui.screens.return_value = [_screen(QRect(0, 0, 1920, 1080))]
        settings = AppSettings(ui=UISettings(stos_browser_folder="/tmp/stos"))
        anchor = MagicMock()
        browser = MagicMock()
        browser.minimum_layout_width.return_value = 200
        StosWindow._folder_browser = browser
        try:
            StosWindow.open_folder_browser_if_cached_folder_exists(
                settings, anchor, geometry_restored=False)
        finally:
            StosWindow._folder_browser = None
        mock_layout.assert_called_once_with(anchor._window_manager)
        anchor._layout_browser_left_of_composite.assert_not_called()


class TestBrowserMinimumLayoutWidth(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication(sys.argv)

    def test_minimum_width_fits_long_manual_label(self) -> None:
        from pyre.stos_manual_paths import BrowseMode, StosBrowserRow
        from pyre.ui.windows.stosfilebrowser import StosFileBrowserWindow

        browser = StosFileBrowserWindow(parent=None, settings=AppSettings())
        browser._rows = [
            StosBrowserRow(
                basename="73-74_ctrl-TEM_Blob_map-TEM_Blob.stos",
                auto_path="/a.stos",
                manual_path="/m.stos",
            ),
        ]
        browser._browse_mode = BrowseMode.stos_group
        width = browser.minimum_layout_width()
        self.assertGreaterEqual(width, 180)


class TestSingleMonitorCompositeLayout(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication(sys.argv)

    def _window_manager(self):
        from pyre.interfaces.viewtype import ViewType

        source = MagicMock(spec=QMainWindow)
        target = MagicMock(spec=QMainWindow)
        composite = MagicMock(spec=QMainWindow)
        windows = {
            ViewType.Source: source,
            ViewType.Target: target,
            ViewType.Composite: composite,
        }
        window_manager = MagicMock()
        window_manager.__contains__ = lambda _self, key: key in windows
        window_manager.__getitem__ = lambda _self, key: windows[key]
        return window_manager, source, target, composite

    @patch("pyre.ui.windows.stoswindow.StosWindow.sync_window_visibility_menus")
    @patch("PyQt6.QtGui.QGuiApplication")
    def test_hides_source_target_and_fills_work_area(
            self, mock_qgui: MagicMock, _sync: MagicMock) -> None:
        from pyre.ui.windows.stoswindow import StosWindow

        mock_qgui.screens.return_value = [_screen(QRect(0, 0, 1920, 1080))]
        window_manager, source, target, composite = self._window_manager()

        old_browser = StosWindow._folder_browser
        StosWindow._folder_browser = None
        try:
            with patch("pyre.ui.windows.stoswindow.apply_frame_geometry_to_widget") as mock_apply:
                StosWindow.apply_single_monitor_composite_layout(window_manager)
        finally:
            StosWindow._folder_browser = old_browser

        source.hide.assert_called_once()
        target.hide.assert_called_once()
        composite.show.assert_called_once()
        mock_apply.assert_called_once()
        args = mock_apply.call_args[0]
        self.assertIs(args[0], composite)
        self.assertEqual(args[1], 0)
        self.assertEqual(args[2], 0)
        self.assertEqual(args[3], 1920)
        self.assertEqual(args[4], 1080)

    @patch("pyre.ui.windows.stoswindow.StosWindow.sync_window_visibility_menus")
    @patch("PyQt6.QtGui.QGuiApplication")
    def test_reserves_browser_strip_when_browser_visible(
            self, mock_qgui: MagicMock, _sync: MagicMock) -> None:
        from pyre.ui.windows.stoswindow import StosWindow

        mock_qgui.screens.return_value = [_screen(QRect(0, 0, 1920, 1080))]
        window_manager, source, target, composite = self._window_manager()

        browser = MagicMock()
        browser.isVisible.return_value = True
        browser.width.return_value = 350
        browser.minimum_layout_width.return_value = 200

        old_browser = StosWindow._folder_browser
        StosWindow._folder_browser = browser
        try:
            with patch("pyre.ui.windows.stoswindow.apply_frame_geometry_to_widget") as mock_apply:
                StosWindow.apply_single_monitor_composite_layout(window_manager)
        finally:
            StosWindow._folder_browser = old_browser

        source.hide.assert_called_once()
        target.hide.assert_called_once()
        composite.show.assert_called_once()
        self.assertEqual(mock_apply.call_count, 2)
        browser_args = mock_apply.call_args_list[0][0]
        composite_args = mock_apply.call_args_list[1][0]
        self.assertIs(browser_args[0], browser)
        self.assertEqual(browser_args[1:], (0, 0, 350, 1080))
        self.assertIs(composite_args[0], composite)
        self.assertEqual(composite_args[1:], (350, 0, 1570, 1080))


class TestSingleMonitorAllWindowsLayout(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication(sys.argv)

    @patch("pyre.ui.windows.stoswindow.StosWindow.sync_window_visibility_menus")
    @patch("PyQt6.QtGui.QGuiApplication")
    def test_tiles_source_target_composite_beside_browser(
            self, mock_qgui: MagicMock, _sync: MagicMock) -> None:
        from pyre.interfaces.viewtype import ViewType
        from pyre.ui.windows.stoswindow import StosWindow

        mock_qgui.screens.return_value = [_screen(QRect(0, 0, 1920, 1080))]

        source = MagicMock(spec=QMainWindow)
        target = MagicMock(spec=QMainWindow)
        composite = MagicMock(spec=QMainWindow)
        windows = {
            ViewType.Source: source,
            ViewType.Target: target,
            ViewType.Composite: composite,
        }
        window_manager = MagicMock()
        window_manager.__contains__ = lambda _self, key: key in windows
        window_manager.__getitem__ = lambda _self, key: windows[key]

        browser = MagicMock()
        browser.isVisible.return_value = True
        browser.width.return_value = 320
        browser.minimum_layout_width.return_value = 200

        old_browser = StosWindow._folder_browser
        StosWindow._folder_browser = browser
        try:
            with patch("pyre.ui.windows.stoswindow.apply_frame_geometry_to_widget") as mock_apply:
                StosWindow.apply_single_monitor_all_windows_layout(window_manager)
        finally:
            StosWindow._folder_browser = old_browser

        source.show.assert_called_once()
        target.show.assert_called_once()
        composite.show.assert_called_once()
        self.assertEqual(mock_apply.call_count, 4)
        by_widget = {call.args[0]: call.args[1:] for call in mock_apply.call_args_list}
        self.assertEqual(by_widget[browser], (0, 0, 320, 1080))
        self.assertEqual(by_widget[source], (320, 0, 800, 540))
        self.assertEqual(by_widget[target], (1120, 0, 800, 540))
        self.assertEqual(by_widget[composite], (320, 540, 1600, 540))


if __name__ == "__main__":
    unittest.main()
