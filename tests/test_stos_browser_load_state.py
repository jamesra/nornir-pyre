"""Tests for the Stos Directory load state: loading status, Save STOS gating, load failures.

2026-11-12 incident: after switching browser folders over a slow link, a pair was picked and
saved before its load had applied, so Pyre saved the previous volume's pair into the new folder.
"""

from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
import unittest
from collections.abc import Callable
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import QApplication
from pyre.interfaces.viewtype import ViewType
from pyre.qt_eventmanager import init_main_thread_dispatcher
from pyre.settings.app import AppSettings
from pyre.stos_manual_paths import BrowseMode, StosBrowserRow
from pyre.ui.windows.stosfilebrowser import StosFileBrowserWindow
from pyre.ui.windows.stoswindow import StosWindow

_VIEW_TYPES = (ViewType.Source, ViewType.Target, ViewType.Composite)


class _FakeStatusBar:
    """Minimal QStatusBar stand-in recording the current message."""

    def __init__(self) -> None:
        self.message = ""

    def showMessage(self, message: str, timeout: int = 0) -> None:
        self.message = message

    def clearMessage(self) -> None:
        self.message = ""

    def currentMessage(self) -> str:
        return self.message


def _fake_window_manager() -> tuple[MagicMock, dict[ViewType, _FakeStatusBar]]:
    bars = {view_type: _FakeStatusBar() for view_type in _VIEW_TYPES}
    windows = {view_type: SimpleNamespace(statusBar=lambda b=bar: b) for view_type, bar in bars.items()}
    manager = MagicMock()
    manager.__contains__ = lambda self, key: key in windows
    manager.__getitem__ = lambda self, key: windows[key]
    return manager, bars


class _StosWindowClassStateMixin(unittest.TestCase):
    """Save and restore StosWindow's class-level save/load state around each test."""

    def setUp(self) -> None:
        saved = (
            StosWindow._browser_load_message,
            StosWindow._stos_save_in_progress,
            StosWindow._save_stos_menu_actions,
        )

        def _restore() -> None:
            (StosWindow._browser_load_message,
             StosWindow._stos_save_in_progress,
             StosWindow._save_stos_menu_actions) = saved

        self.addCleanup(_restore)
        StosWindow._browser_load_message = None
        StosWindow._stos_save_in_progress = False
        self.actions = [MagicMock(), MagicMock()]
        StosWindow._save_stos_menu_actions = self.actions


class TestStosWindowBrowserLoadState(_StosWindowClassStateMixin):
    def test_begin_shows_loading_and_disables_save(self) -> None:
        manager, bars = _fake_window_manager()
        StosWindow.begin_browser_load("123-122.stos", window_manager=manager)

        self.assertTrue(StosWindow.browser_load_in_progress())
        for bar in bars.values():
            self.assertEqual(bar.message, "Loading 123-122.stos…")
        for action in self.actions:
            action.setEnabled.assert_called_with(False)

    def test_end_clears_loading_and_enables_save(self) -> None:
        manager, bars = _fake_window_manager()
        StosWindow.begin_browser_load("a.stos", window_manager=manager)
        StosWindow.end_browser_load(window_manager=manager)

        self.assertFalse(StosWindow.browser_load_in_progress())
        for bar in bars.values():
            self.assertEqual(bar.message, "")
        for action in self.actions:
            action.setEnabled.assert_called_with(True)

    def test_end_leaves_other_status_text(self) -> None:
        manager, bars = _fake_window_manager()
        StosWindow.begin_browser_load("a.stos", window_manager=manager)
        bars[ViewType.Composite].showMessage("Saving b.stos…")
        StosWindow.end_browser_load(window_manager=manager)
        self.assertEqual(bars[ViewType.Composite].message, "Saving b.stos…")
        self.assertEqual(bars[ViewType.Source].message, "")

    def test_end_keeps_save_disabled_while_a_save_runs(self) -> None:
        manager, _bars = _fake_window_manager()
        StosWindow.begin_browser_load("a.stos", window_manager=manager)
        StosWindow._stos_save_in_progress = True
        StosWindow.end_browser_load(window_manager=manager)
        for action in self.actions:
            action.setEnabled.assert_called_with(False)

    def test_save_finishing_during_load_keeps_save_disabled(self) -> None:
        manager, _bars = _fake_window_manager()
        StosWindow._stos_save_in_progress = True
        StosWindow.begin_browser_load("a.stos", window_manager=manager)
        StosWindow._clear_stos_save_status()
        for action in self.actions:
            action.setEnabled.assert_called_with(False)

    def test_on_save_stos_is_a_noop_while_loading(self) -> None:
        manager, _bars = _fake_window_manager()
        window = SimpleNamespace(
            _transform_controller=object(),
            _prompt_save_stos_path=MagicMock(return_value="x.stos"),
            _confirm_save_across_volumes=MagicMock(return_value=True),
            _submit_async_stos_save=MagicMock(),
        )
        StosWindow.begin_browser_load("a.stos", window_manager=manager)
        StosWindow.onSaveStos(window)  # type: ignore[arg-type]
        window._prompt_save_stos_path.assert_not_called()
        window._submit_async_stos_save.assert_not_called()

        StosWindow.end_browser_load(window_manager=manager)
        StosWindow.onSaveStos(window)  # type: ignore[arg-type]
        window._submit_async_stos_save.assert_called_once_with("x.stos")

    def test_on_save_stos_cancelled_volume_warning_does_not_save(self) -> None:
        window = SimpleNamespace(
            _transform_controller=object(),
            _prompt_save_stos_path=MagicMock(return_value="x.stos"),
            _confirm_save_across_volumes=MagicMock(return_value=False),
            _submit_async_stos_save=MagicMock(),
        )
        StosWindow.onSaveStos(window)  # type: ignore[arg-type]
        window._confirm_save_across_volumes.assert_called_once_with("x.stos")
        window._submit_async_stos_save.assert_not_called()


class TestStosBrowserLoadLifecycle(_StosWindowClassStateMixin):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication(sys.argv)
        init_main_thread_dispatcher()

    def setUp(self) -> None:
        super().setUp()
        self.begin = MagicMock()
        self.end = MagicMock()
        self.apply = MagicMock()
        self.message_box = MagicMock()
        for target, attr, mock in (
                (StosWindow, "begin_browser_load", self.begin),
                (StosWindow, "end_browser_load", self.end),
                (StosWindow, "apply_stos_load_result", self.apply)):
            patcher = patch.object(target, attr, mock)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch("pyre.ui.windows.stosfilebrowser.QMessageBox", self.message_box)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.browser = StosFileBrowserWindow(parent=None, settings=AppSettings())
        self.browser._folder = "/data/RC1_Crush/TEM/Brute32"
        self.browser._browse_mode = BrowseMode.stos_group
        self.browser._rows = [
            StosBrowserRow(basename=f"{i}.stos", auto_path=f"/data/{i}.stos", manual_path=None)
            for i in range(3)
        ]
        self.browser._populate_list()
        self.addCleanup(lambda: self.browser.closeEvent(QCloseEvent()))

    def _patch_load(self, side_effect: Callable[[str], object]) -> None:
        patcher = patch.object(StosWindow, "load_stos_data", side_effect=side_effect)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _wait_for(self, predicate: Callable[[], bool], timeout_s: float = 5.0) -> None:
        deadline = time.monotonic() + timeout_s
        while not predicate():
            if time.monotonic() > deadline:
                self.fail("timed out waiting for the browser load to finish")
            self._app.processEvents()
            time.sleep(0.01)

    # Browsers left over from other test modules may still fire their own debounced loads
    # into these class-level mocks, so every check filters to this test's browser and paths.
    def _applied_paths(self) -> list[str]:
        return [c.args[0] for c in self.apply.call_args_list if str(c.args[0]).startswith("/data/")]

    def _warnings(self) -> list[str]:
        """Text of each failure message box parented to this test's browser."""
        return [c.args[2] for c in self.message_box.call_args_list if c.args[-1] is self.browser]

    def _wait_for_load_done(self) -> None:
        self._wait_for(lambda: not self.browser._load_active)

    def test_success_starts_and_clears_loading(self) -> None:
        self._patch_load(lambda path: "decoded")
        self.browser._load_stos_path("/data/1.stos", 1, browser_basename="1.stos")
        self.begin.assert_any_call("1.stos")
        self.assertTrue(self.browser._load_active)

        self._wait_for_load_done()
        self.assertEqual(self._applied_paths(), ["/data/1.stos"])
        self.end.assert_called()
        self.assertEqual(self._warnings(), [])

    def test_decode_failure_clears_loading_and_warns(self) -> None:
        def _fail(path: str) -> object:
            raise OSError("network name no longer available")

        self._patch_load(_fail)
        self.browser._load_stos_path("/data/1.stos", 1, browser_basename="1.stos")
        self._wait_for_load_done()

        self.assertEqual(self._applied_paths(), [])
        self.end.assert_called()
        warnings = self._warnings()
        self.assertEqual(len(warnings), 1)
        self.assertIn("Could not open 1.stos", warnings[0])
        self.assertIn("previously open pair is still shown", warnings[0])
        self.assertIn("network name no longer available", warnings[0])

    def test_apply_failure_clears_loading_and_warns(self) -> None:
        self._patch_load(lambda path: "decoded")
        self.apply.side_effect = ValueError("bad transform")
        self.browser._load_stos_path("/data/1.stos", 1, browser_basename="1.stos")
        self._wait_for_load_done()
        warnings = self._warnings()
        self.assertEqual(len(warnings), 1)
        self.assertIn("bad transform", warnings[0])

    def test_superseded_failure_is_silent_and_newer_load_applies(self) -> None:
        release_first = threading.Event()

        def _load(path: str) -> object:
            if path.endswith("0.stos"):
                release_first.wait(5.0)
                raise OSError("first load failed")
            return "decoded-2"

        self._patch_load(_load)
        self.browser._load_stos_path("/data/0.stos", 0, browser_basename="0.stos")
        self.browser._execute_pending_load()  # first load now blocks in the worker
        self.browser._load_stos_path("/data/2.stos", 2, browser_basename="2.stos")
        release_first.set()

        self._wait_for_load_done()
        self.assertEqual(self._warnings(), [])
        self.assertEqual(self._applied_paths(), ["/data/2.stos"])

    def test_superseded_failure_does_not_clear_pending_newer_load(self) -> None:
        release_first = threading.Event()
        first_done = threading.Event()

        def _load(path: str) -> object:
            release_first.wait(5.0)
            first_done.set()
            raise OSError("first load failed")

        self._patch_load(_load)
        self.browser._load_stos_path("/data/0.stos", 0, browser_basename="0.stos")
        self.browser._execute_pending_load()
        self.browser._load_stos_path("/data/2.stos", 2, browser_basename="2.stos")
        self.browser._debounce_timer.stop()  # keep the newer load pending
        release_first.set()
        self._wait_for(first_done.is_set)
        for _ in range(20):
            self._app.processEvents()
            time.sleep(0.01)

        self.assertEqual(self._warnings(), [])
        self.assertTrue(self.browser._load_active)

    def test_load_keeps_folder_from_when_row_was_picked(self) -> None:
        self._patch_load(lambda path: "decoded")
        self.browser._load_stos_path("/data/1.stos", 1, browser_basename="1.stos")
        self.browser._folder = "/data/RC3/TEM/Brute32"  # folder changes before the load runs
        self._wait_for_load_done()
        mine = [c for c in self.apply.call_args_list if c.args[0] == "/data/1.stos"]
        self.assertEqual(len(mine), 1)
        self.assertEqual(mine[0].kwargs["browser_folder"], "/data/RC1_Crush/TEM/Brute32")

    def test_close_clears_loading_state(self) -> None:
        self._patch_load(lambda path: "decoded")
        self.browser._load_stos_path("/data/1.stos", 1, browser_basename="1.stos")
        self.end.reset_mock()
        self.browser.closeEvent(QCloseEvent())
        self.end.assert_called()
        self.assertFalse(self.browser._load_active)

    def test_folder_change_clears_open_pair_title_and_highlight(self) -> None:
        self._patch_load(lambda path: "decoded")
        self.browser._load_stos_path("/data/1.stos", 1, browser_basename="1.stos")
        self._wait_for_load_done()
        self.assertIn("1.stos", self.browser.windowTitle())

        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "5-4.stos"), "w", encoding="utf-8") as handle:
                handle.write("stub")
            self.browser._apply_folder(tmp, persist=False, confirm_manual=False)
            self.assertEqual(self.browser.windowTitle(), "Stos Directory")
            self.assertEqual(self.browser._current_index, -1)
            self.browser.wait_for_scan_idle()
            self._app.processEvents()
            self.assertEqual(self.browser._list_widget.currentRow(), -1)
            self.assertEqual(self.browser._list_widget.selectedItems(), [])


if __name__ == "__main__":
    unittest.main()
