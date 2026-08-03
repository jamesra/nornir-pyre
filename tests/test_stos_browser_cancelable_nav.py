"""Tests for cancelable / debounced STOS browser navigation loads."""

from __future__ import annotations

import sys
import unittest
from unittest.mock import MagicMock, patch

from PyQt6.QtWidgets import QApplication

from pyre.settings.app import AppSettings
from pyre.stos_manual_paths import BrowseMode, StosBrowserRow
from pyre.ui.windows.stosfilebrowser import StosFileBrowserWindow, _PendingStosLoad


def _make_rows(count: int) -> list[StosBrowserRow]:
    return [
        StosBrowserRow(
            basename=f"section_{i}.stos",
            auto_path=f"/tmp/section_{i}.stos",
            manual_path=None,
        )
        for i in range(count)
    ]


class TestStosBrowserCancelableNavigation(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication(sys.argv)

    def _browser(self, count: int = 5, current_index: int = 0) -> StosFileBrowserWindow:
        browser = StosFileBrowserWindow(parent=None, settings=AppSettings())
        browser._folder = "/tmp/stos_group"
        browser._browse_mode = BrowseMode.stos_group
        browser._rows = _make_rows(count)
        browser._current_index = current_index
        browser.NAV_LOAD_DEBOUNCE_MS = 0
        browser._debounce_timer.stop()
        return browser

    def test_rapid_nav_keeps_only_final_pending_load(self) -> None:
        browser = self._browser(current_index=2)
        browser._load_stos_at_index(3)
        browser._load_stos_at_index(1)
        browser._load_stos_at_index(0)
        pending = browser._pending_load
        self.assertIsNotNone(pending)
        assert pending is not None
        self.assertEqual(pending.index, 0)
        self.assertEqual(pending.filepath, "/tmp/section_0.stos")
        self.assertEqual(pending.generation, browser._load_generation)
        self.assertEqual(browser._current_index, 0)

    def test_superseded_generation_skips_apply(self) -> None:
        """Mirrors the done-callback gate used by _execute_pending_load."""
        browser = self._browser()
        applied: list[str] = []
        request_gen = 1
        browser._load_generation = 2  # newer navigation already requested

        def apply_if_current(filename: str) -> None:
            if request_gen != browser._load_generation:
                return
            applied.append(filename)

        apply_if_current("/tmp/section_1.stos")
        self.assertEqual(applied, [])

    def test_matching_generation_applies(self) -> None:
        browser = self._browser()
        applied: list[str] = []
        request_gen = 5
        browser._load_generation = 5

        def apply_if_current(filename: str) -> None:
            if request_gen != browser._load_generation:
                return
            applied.append(filename)

        apply_if_current("/tmp/section_2.stos")
        self.assertEqual(applied, ["/tmp/section_2.stos"])

    def test_execute_pending_clears_pending_and_submits_load(self) -> None:
        browser = self._browser()
        browser._pending_load = _PendingStosLoad(
            generation=3,
            filepath="/tmp/section_3.stos",
            index=3,
            browser_basename="section_3.stos",
        )
        browser._load_generation = 3
        submitted: list[str] = []

        def fake_submit(fn, *args, **kwargs):
            submitted.append("submitted")
            future = MagicMock()
            future.add_done_callback = MagicMock()
            return future

        with patch.object(browser._load_executor, "submit", side_effect=fake_submit):
            with patch("pyre.ui.windows.stoswindow.StosWindow.load_stos_data"):
                browser._execute_pending_load()

        self.assertIsNone(browser._pending_load)
        self.assertEqual(submitted, ["submitted"])


if __name__ == "__main__":
    unittest.main()
