"""Stos Browser background ZNCC scoring: incremental cache saves and no scoring while hidden."""

from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
import unittest
from typing import Any
from unittest.mock import patch

from nornir_imageregistration.stos_quality import (
    PairZnccResult,
    QualityCache,
    merge_entry,
    save_quality_cache,
)
from PyQt6.QtWidgets import QApplication
from pyre.qt_eventmanager import init_main_thread_dispatcher
from pyre.settings.app import AppSettings
from pyre.stos_manual_paths import BrowseMode, StosFileSource, scan_stos_browser_rows
from pyre.ui.windows.stosfilebrowser import StosFileBrowserWindow

_SCORE = "pyre.ui.windows.stosfilebrowser.score_stos_into_cache"
_SAVE = "pyre.ui.windows.stosfilebrowser.save_quality_cache"
_INTERVAL = "pyre.ui.windows.stosfilebrowser._QUALITY_CACHE_SAVE_INTERVAL_S"
_STALE_PATHS = "pyre.ui.windows.stosfilebrowser.stale_quality_score_paths"


def _stub_stos_folder(tmp: str, count: int) -> list[str]:
    """Write *count* placeholder ``.stos`` files and return their paths."""
    paths = []
    for index in range(count):
        path = os.path.join(tmp, f"pair{index}.stos")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("stub")
        paths.append(path)
    return paths


def _fake_score(scored: list[str]):
    """Return a score_stos_into_cache stand-in that records paths and reports a computed score."""
    def score(_folder: str, path: str, *, cache: QualityCache, **_kwargs: Any):
        scored.append(path)
        return cache, {}, True
    return score


class TestStosBrowserQualityScoring(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication(sys.argv)
        init_main_thread_dispatcher()

    def _browser(self, folder: str) -> StosFileBrowserWindow:
        browser = StosFileBrowserWindow(parent=None, settings=AppSettings())
        browser._folder = folder
        browser._browse_mode = BrowseMode.stos_group
        browser._rows = scan_stos_browser_rows(folder, BrowseMode.stos_group)
        self.addCleanup(browser.close)
        return browser

    def test_hidden_window_defers_scoring(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _stub_stos_folder(tmp, 2)
            browser = self._browser(tmp)
            scored: list[str] = []
            with patch(_SCORE, side_effect=_fake_score(scored)):
                browser._queue_quality_scores(paths)
            self.assertIsNone(browser._score_future)
            self.assertTrue(browser._quality_scores_incomplete)
            self.assertEqual(scored, [])

    def test_showing_the_window_scores_what_was_deferred(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _stub_stos_folder(tmp, 2)
            browser = self._browser(tmp)
            scored: list[str] = []
            with patch(_SCORE, side_effect=_fake_score(scored)), patch(_SAVE):
                browser._queue_quality_scores(paths)
                browser.show()
                browser.wait_for_scan_idle()
                assert browser._score_future is not None
                browser._score_future.result(timeout=5.0)
            self.assertEqual(sorted(scored), sorted(paths))
            self.assertFalse(browser._quality_scores_incomplete)

    def test_minimized_window_defers_until_restored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _stub_stos_folder(tmp, 1)
            browser = self._browser(tmp)
            browser.showMinimized()
            self._app.processEvents()
            scored: list[str] = []
            with patch(_SCORE, side_effect=_fake_score(scored)), patch(_SAVE):
                browser._queue_quality_scores(paths)
                self.assertIsNone(browser._score_future)
                browser.showNormal()
                self._app.processEvents()
                browser.wait_for_scan_idle()
                assert browser._score_future is not None
                browser._score_future.result(timeout=5.0)
            self.assertEqual(scored, paths)

    def test_cache_is_saved_during_scoring_not_only_at_the_end(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _stub_stos_folder(tmp, 3)
            browser = self._browser(tmp)
            browser.show()
            scored: list[str] = []
            with patch(_SCORE, side_effect=_fake_score(scored)), patch(_SAVE) as save, \
                    patch(_INTERVAL, 0.0):
                browser._queue_quality_scores(paths)
                assert browser._score_future is not None
                browser._score_future.result(timeout=5.0)
            self.assertEqual(len(scored), 3)
            self.assertEqual(save.call_count, 3)

    def test_cancelled_scoring_saves_what_it_scored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _stub_stos_folder(tmp, 3)
            browser = self._browser(tmp)
            browser.show()
            scored: list[str] = []

            def score_then_cancel(folder: str, path: str, *, cache: QualityCache, **kwargs: Any):
                result = _fake_score(scored)(folder, path, cache=cache, **kwargs)
                browser._score_generation += 1  # as a rescan or close would
                return result

            with patch(_SCORE, side_effect=score_then_cancel), patch(_SAVE) as save:
                browser._queue_quality_scores(paths)
                assert browser._score_future is not None
                browser._score_future.result(timeout=5.0)
            self.assertEqual(len(scored), 1)
            self.assertEqual(save.call_count, 1)

    def test_closing_mid_scoring_resumes_on_reopen(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = _stub_stos_folder(tmp, 2)
            browser = self._browser(tmp)
            browser.show()
            started = threading.Event()
            release = threading.Event()
            scored: list[str] = []

            def blocking_score(folder: str, path: str, *, cache: QualityCache, **kwargs: Any):
                started.set()
                release.wait(5.0)
                return _fake_score(scored)(folder, path, cache=cache, **kwargs)

            with patch(_SCORE, side_effect=blocking_score), patch(_SAVE):
                browser._queue_quality_scores(paths)
                first = browser._score_future
                assert first is not None
                self.assertTrue(started.wait(5.0))
                browser.close()
                self.assertTrue(browser._quality_scores_incomplete)
                release.set()
                first.result(timeout=5.0)

                browser.show()
                browser.wait_for_scan_idle()
                second = browser._score_future
                assert second is not None
                self.assertIsNot(second, first)
                second.result(timeout=5.0)
            self.assertEqual(sorted(set(scored)), sorted(paths))

    def test_scan_idle_waits_for_scoring_the_scan_started(self) -> None:
        """wait_for_scan_idle returns only once scoring started by the scan has ended.

        Scoring can write stos_quality.json into the folder. A test that removed its
        temporary folder as soon as the scan finished raced that write, and cleanup
        failed with "directory is not empty" on a loaded machine.
        """
        with tempfile.TemporaryDirectory() as tmp:
            paths = _stub_stos_folder(tmp, 2)
            browser = StosFileBrowserWindow(parent=None, settings=AppSettings())
            self.addCleanup(browser.close)
            browser.show()
            scored: list[str] = []
            started = threading.Event()

            def slow_score(folder: str, path: str, *, cache: QualityCache, **kwargs: Any):
                started.set()
                time.sleep(0.2)
                return _fake_score(scored)(folder, path, cache=cache, **kwargs)

            with patch(_SCORE, side_effect=slow_score), patch(_SAVE):
                browser._apply_folder(tmp, persist=False, confirm_manual=False)
                browser.wait_for_scan_idle()
                self.assertTrue(started.is_set(), "the scan should have started scoring")
                assert browser._score_future is not None
                self.assertTrue(browser._score_future.done())
            self.assertEqual(sorted(scored), sorted(paths))

    def test_reopened_window_can_rescan(self) -> None:
        """closeEvent shuts the executor down; showing the window again replaces it."""
        with tempfile.TemporaryDirectory() as tmp:
            _stub_stos_folder(tmp, 1)
            browser = self._browser(tmp)
            browser.show()
            browser.close()
            browser.show()
            with patch(_SCORE, side_effect=_fake_score([])), patch(_SAVE):
                browser.rescan()
                browser.wait_for_scan_idle()
            self.assertEqual(len(browser._rows), 1)

    def test_cached_scores_paint_before_checksum_validation_finishes(self) -> None:
        """stos_quality.json scores reach the table before LoadChecksum walks the folder."""
        with tempfile.TemporaryDirectory() as tmp:
            paths = _stub_stos_folder(tmp, 1)
            cache = QualityCache()
            merge_entry(
                cache,
                os.path.basename(paths[0]),
                pair=PairZnccResult(
                    pair_zncc=0.42,
                    downsample=16.0,
                    stos_checksum='cached',
                    stos_mtime_ns=os.stat(paths[0]).st_mtime_ns,
                    max_side=2048,
                ),
            )
            save_quality_cache(tmp, cache)

            browser = self._browser(tmp)
            browser.show()
            self._app.processEvents()
            generation = browser._scan_generation
            entered = threading.Event()
            release = threading.Event()

            def slow_stale(*_args: Any, **_kwargs: Any) -> list[str]:
                entered.set()
                release.wait(5.0)
                return []

            with patch(_STALE_PATHS, side_effect=slow_stale), patch(_SCORE), patch(_SAVE):
                future = browser._load_executor.submit(
                    browser._attach_cached_scores_then_validate,
                    tmp,
                    list(browser._rows),
                    StosFileSource.auto,
                    generation,
                )
                self.assertTrue(entered.wait(5.0))
                deadline = time.monotonic() + 5.0
                while time.monotonic() < deadline:
                    self._app.processEvents()
                    if (
                        browser._rows
                        and browser._rows[0].quality_score == 0.42
                    ):
                        break
                    time.sleep(0.01)
                else:
                    self.fail("cached score was not painted before checksum validation finished")
                release.set()
                future.result(timeout=5.0)
                browser.wait_for_scan_idle()
            self.assertEqual(browser._rows[0].quality_score, 0.42)


if __name__ == "__main__":
    unittest.main()
