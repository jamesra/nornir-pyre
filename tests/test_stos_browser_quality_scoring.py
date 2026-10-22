"""Stos Browser background ZNCC scoring: incremental cache saves and no scoring while hidden."""

from __future__ import annotations

import os
import sys
import tempfile
import threading
import unittest
from typing import Any
from unittest.mock import patch

from nornir_imageregistration.stos_quality import QualityCache
from PyQt6.QtWidgets import QApplication
from pyre.qt_eventmanager import init_main_thread_dispatcher
from pyre.settings.app import AppSettings
from pyre.stos_manual_paths import BrowseMode, scan_stos_browser_rows
from pyre.ui.windows.stosfilebrowser import StosFileBrowserWindow

_SCORE = "pyre.ui.windows.stosfilebrowser.score_stos_into_cache"
_SAVE = "pyre.ui.windows.stosfilebrowser.save_quality_cache"
_INTERVAL = "pyre.ui.windows.stosfilebrowser._QUALITY_CACHE_SAVE_INTERVAL_S"


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


if __name__ == "__main__":
    unittest.main()
