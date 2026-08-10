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
from pyre.settings.app import AppSettings
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


if __name__ == "__main__":
    unittest.main()
