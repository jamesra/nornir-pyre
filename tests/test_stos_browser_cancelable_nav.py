"""Tests for cancelable / debounced STOS browser navigation loads."""

from __future__ import annotations

import sys
import threading
import time
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

        def _row_from_memory(index: int) -> StosBrowserRow:
            return browser._rows[index]

        def _fake_resolve(row: StosBrowserRow, source: object) -> tuple[str, object]:
            return row.auto_path, source

        with patch.object(browser, "_refresh_row_from_disk", side_effect=_row_from_memory), \
                patch.object(browser, "_resolve_load_path_for_row", side_effect=_fake_resolve), \
                patch("pyre.ui.windows.stosfilebrowser.QMessageBox.information"):
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

        with patch.object(browser._stos_load_executor, "submit", side_effect=fake_submit):
            with patch("pyre.ui.windows.stoswindow.StosWindow.load_stos_data"):
                browser._execute_pending_load()

        self.assertIsNone(browser._pending_load)
        self.assertEqual(submitted, ["submitted"])

    def test_stos_open_uses_dedicated_executor_not_background_pool(self) -> None:
        """Checksum validation shares the bg pool; opens must not wait behind it."""
        browser = self._browser()
        browser._pending_load = _PendingStosLoad(
            generation=1,
            filepath="/tmp/section_1.stos",
            index=1,
            browser_basename="section_1.stos",
        )
        browser._load_generation = 1
        bg_submits: list[str] = []
        load_submits: list[str] = []

        def bg_submit(fn, *args, **kwargs):
            bg_submits.append("bg")
            future = MagicMock()
            future.add_done_callback = MagicMock()
            return future

        def load_submit(fn, *args, **kwargs):
            load_submits.append("load")
            future = MagicMock()
            future.add_done_callback = MagicMock()
            return future

        with patch.object(browser._load_executor, "submit", side_effect=bg_submit), \
                patch.object(browser._stos_load_executor, "submit", side_effect=load_submit), \
                patch("pyre.ui.windows.stoswindow.StosWindow.load_stos_data"):
            browser._execute_pending_load()

        self.assertEqual(load_submits, ["load"])
        self.assertEqual(bg_submits, [])

    def test_stos_open_completes_while_background_pool_is_saturated(self) -> None:
        """Regression: folder-wide LoadChecksum used to starve STOS opens on the shared pool."""
        browser = self._browser()
        release = threading.Event()
        self.addCleanup(release.set)
        self.addCleanup(browser.close)
        started = threading.Barrier(4)  # 3 bg workers + main

        def block_forever() -> None:
            started.wait(5.0)
            release.wait(10.0)

        for _ in range(3):
            browser._load_executor.submit(block_forever)
        self.assertTrue(started.wait(5.0), "background workers did not all start")

        loaded = threading.Event()

        def fake_load(_path: str) -> object:
            loaded.set()
            return object()

        browser._pending_load = _PendingStosLoad(
            generation=1,
            filepath="/tmp/section_1.stos",
            index=1,
            browser_basename="section_1.stos",
        )
        browser._load_generation = 1
        with patch("pyre.ui.windows.stoswindow.StosWindow.load_stos_data", side_effect=fake_load), \
                patch("pyre.ui.windows.stoswindow.StosWindow.apply_stos_load_result"):
            browser._execute_pending_load()
            self.assertTrue(loaded.wait(2.0), "STOS open stayed queued behind background work")
        release.set()

    def test_choosing_a_stos_cancels_in_flight_registrations(self) -> None:
        browser = self._browser()
        with patch.object(browser, "_cancel_in_flight_registrations") as cancel:
            browser._load_stos_path("/tmp/section_0.stos", 0)
            cancel.assert_called_once()


if __name__ == "__main__":
    unittest.main()
