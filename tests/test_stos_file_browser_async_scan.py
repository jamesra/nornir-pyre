"""Tests for async Stos Browser folder scan and generation guards."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from unittest.mock import patch

from PyQt6.QtWidgets import QApplication

from nornir_imageregistration.stos_quality import QualityCache
from pyre.qt_eventmanager import init_main_thread_dispatcher
from pyre.settings.app import AppSettings, StosSettings, UISettings
from pyre.stos_manual_paths import BrowseMode, StosBrowserRow, scan_stos_browser_rows
from pyre.stos_quality_browser import format_quality_score
from pyre.ui.windows.stosfilebrowser import StosFileBrowserWindow


def _touch(path: str) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("stub")


class TestStosFileBrowserAsyncScan(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication(sys.argv)
        init_main_thread_dispatcher()

    def test_name_only_populate_does_not_require_attach(self) -> None:
        """Name-first fill shows basenames with em-dash scores without quality attach."""
        with tempfile.TemporaryDirectory() as tmp:
            _touch(os.path.join(tmp, "a.stos"))
            _touch(os.path.join(tmp, "b.stos"))
            rows = scan_stos_browser_rows(tmp, BrowseMode.stos_group)
            browser = StosFileBrowserWindow(parent=None, settings=AppSettings())
            browser._folder = tmp
            browser._browse_mode = BrowseMode.stos_group
            browser._rows = rows

            with patch(
                    "pyre.ui.windows.stosfilebrowser.attach_quality_scores",
            ) as mock_attach:
                browser._populate_list_from_rows(rows, scores_ready=False)
                mock_attach.assert_not_called()

            self.assertEqual(browser._list_widget.rowCount(), 2)
            self.assertEqual(browser._list_widget.item(0, 0).text(), "a.stos")
            self.assertEqual(
                browser._list_widget.item(0, 1).text(),
                format_quality_score(None),
            )

    def test_apply_folder_fills_names_then_completes_attach(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _touch(os.path.join(tmp, "pair.stos"))
            browser = StosFileBrowserWindow(parent=None, settings=AppSettings())
            browser._apply_folder(tmp, persist=False, confirm_manual=False)
            browser.wait_for_scan_idle()

            self.assertEqual(len(browser._rows), 1)
            self.assertEqual(browser._rows[0].basename, "pair.stos")
            self.assertEqual(browser._list_widget.rowCount(), 1)
            self.assertEqual(browser._folder_label.text(), tmp)

    def test_stale_scan_generation_callbacks_ignored(self) -> None:
        browser = StosFileBrowserWindow(parent=None, settings=AppSettings())
        browser._folder = "/tmp/stos_group"
        browser._browse_mode = BrowseMode.stos_group
        browser._scan_generation = 2
        rows = [
            StosBrowserRow(
                basename="stale.stos",
                auto_path="/tmp/stos_group/stale.stos",
                manual_path=None,
            ),
        ]

        browser._on_scan_rows_ready("/tmp/stos_group", rows, generation=1)
        self.assertEqual(browser._rows, [])
        self.assertEqual(browser._list_widget.rowCount(), 0)

        browser._on_quality_attach_ready(
            "/tmp/stos_group",
            rows,
            QualityCache(),
            stale=[],
            generation=1,
        )
        self.assertEqual(browser._rows, [])
        self.assertNotEqual(browser._last_completed_scan_generation, 1)

    def test_matching_generation_applies_rows(self) -> None:
        browser = StosFileBrowserWindow(parent=None, settings=AppSettings())
        browser._folder = "/tmp/stos_group"
        browser._browse_mode = BrowseMode.stos_group
        browser._scan_generation = 3
        rows = [
            StosBrowserRow(
                basename="ok.stos",
                auto_path="/tmp/stos_group/ok.stos",
                manual_path=None,
                quality_score=0.5,
            ),
        ]

        browser._on_scan_rows_ready("/tmp/stos_group", rows, generation=3)
        self.assertEqual(len(browser._rows), 1)
        self.assertEqual(browser._list_widget.item(0, 1).text(), format_quality_score(None))

        browser._on_quality_attach_ready(
            "/tmp/stos_group",
            rows,
            QualityCache(),
            stale=[],
            generation=3,
        )
        self.assertEqual(browser._last_completed_scan_generation, 3)
        self.assertEqual(browser._list_widget.item(0, 1).text(), "0.500")

    def test_startup_selects_last_session_mid_list_file(self) -> None:
        """Cached folder + last-loaded STOS selects that row after the async scan."""
        with tempfile.TemporaryDirectory() as tmp:
            names = ("a_pair.stos", "m_pair.stos", "z_pair.stos")
            for name in names:
                _touch(os.path.join(tmp, name))
            mid = os.path.join(tmp, "m_pair.stos")
            settings = AppSettings(
                ui=UISettings(stos_browser_folder=tmp),
                stos=StosSettings(
                    stos_filename=mid,
                    stos_browser_basename="m_pair.stos",
                ),
            )
            browser = StosFileBrowserWindow(parent=None, settings=settings)
            browser.wait_for_scan_idle()
            expected = next(
                index for index, row in enumerate(browser._rows)
                if row.basename == "m_pair.stos")
            self.assertGreater(expected, 0)
            self.assertLess(expected, len(browser._rows) - 1)
            self.assertEqual(browser._current_index, expected)
            self.assertEqual(browser._list_widget.currentRow(), expected)
            self.assertIsNone(browser._pending_select_path)

    def test_set_current_file_selects_immediately_when_rows_exist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("a_pair.stos", "m_pair.stos", "z_pair.stos"):
                _touch(os.path.join(tmp, name))
            browser = StosFileBrowserWindow(parent=None, settings=AppSettings())
            with patch(
                    "pyre.ui.windows.stosfilebrowser.attach_quality_scores",
                    side_effect=lambda folder, rows, source, cache=None: (list(rows), QualityCache(), []),
            ):
                browser._apply_folder(tmp, persist=False, confirm_manual=False)
                browser.wait_for_scan_idle()
            mid = os.path.join(tmp, "m_pair.stos")
            browser.set_current_file(mid)
            expected = next(
                index for index, row in enumerate(browser._rows)
                if row.basename == "m_pair.stos")
            self.assertEqual(browser._current_index, expected)
            self.assertEqual(browser._list_widget.currentRow(), expected)

    def test_set_current_file_no_match_clears_selection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _touch(os.path.join(tmp, "pair.stos"))
            browser = StosFileBrowserWindow(parent=None, settings=AppSettings())
            with patch(
                    "pyre.ui.windows.stosfilebrowser.attach_quality_scores",
                    side_effect=lambda folder, rows, source, cache=None: (list(rows), QualityCache(), []),
            ):
                browser._apply_folder(tmp, persist=False, confirm_manual=False)
                browser.wait_for_scan_idle()
            browser.set_current_file(os.path.join(tmp, "pair.stos"))
            self.assertEqual(browser._current_index, 0)
            browser.set_current_file(os.path.join(tmp, "missing.stos"))
            self.assertEqual(browser._current_index, -1)
            self.assertEqual(browser._list_widget.currentRow(), -1)
            self.assertIsNone(browser._pending_select_path)


if __name__ == "__main__":
    unittest.main()
