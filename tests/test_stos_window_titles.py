"""Tests for STOS window title formatting."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from pyre.interfaces.viewtype import ViewType
from pyre.settings import AppSettings, ImageAndMaskPath, StosSettings
from pyre.ui.windows.stoswindow import (
    _STOS_WINDOW_BASE_TITLES,
    format_stos_window_title,
    StosWindow,
)


class TestFormatStosWindowTitle(unittest.TestCase):
    """format_stos_window_title appends basename only when path is known."""

    def test_none_path_returns_base_only(self) -> None:
        self.assertEqual(format_stos_window_title("Source Image", None), "Source Image")

    def test_empty_path_returns_base_only(self) -> None:
        self.assertEqual(format_stos_window_title("Source Image", ""), "Source Image")

    def test_absolute_path_uses_basename(self) -> None:
        title = format_stos_window_title(
            "Composite Image",
            r"D:\data\sections\pair_12.stos",
        )
        self.assertEqual(title, "Composite Image — pair_12.stos")

    def test_relative_filename_unchanged(self) -> None:
        title = format_stos_window_title("Target Image", "mosaic.tif")
        self.assertEqual(title, "Target Image — mosaic.tif")


class TestUpdateWindowTitles(unittest.TestCase):
    """update_window_titles sets all three STOS panel titles from settings."""

    def test_sets_source_target_composite_titles(self) -> None:
        settings = AppSettings()
        settings.stos = StosSettings(
            stos_filename=r"C:\work\align.stos",
            source_image=ImageAndMaskPath(
                image_fullpath=r"C:\work\mapped.png", mask_fullpath=None),
            target_image=ImageAndMaskPath(
                image_fullpath=r"C:\work\control.tif", mask_fullpath=None),
        )
        window_manager = MagicMock()
        windows = {
            ViewType.Source: MagicMock(),
            ViewType.Target: MagicMock(),
            ViewType.Composite: MagicMock(),
        }
        window_manager.__contains__ = lambda self, key: key in windows
        window_manager.__getitem__ = lambda self, key: windows[key]

        StosWindow.update_window_titles(settings, window_manager)

        windows[ViewType.Source].setWindowTitle.assert_called_once_with(
            format_stos_window_title(
                _STOS_WINDOW_BASE_TITLES[ViewType.Source], r"C:\work\mapped.png"))
        windows[ViewType.Target].setWindowTitle.assert_called_once_with(
            format_stos_window_title(
                _STOS_WINDOW_BASE_TITLES[ViewType.Target], r"C:\work\control.tif"))
        windows[ViewType.Composite].setWindowTitle.assert_called_once_with(
            format_stos_window_title(
                _STOS_WINDOW_BASE_TITLES[ViewType.Composite], r"C:\work\align.stos"))


if __name__ == "__main__":
    unittest.main()
