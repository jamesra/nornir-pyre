"""Headless tests for STOS Manual override path helpers."""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path

_PYRE_ROOT = Path(__file__).resolve().parents[1]
_PYRE_PACKAGE = _PYRE_ROOT / "pyre"


def _load_stos_manual_paths_module():
    """Load stos_manual_paths without importing pyre package __init__ (Qt/OpenGL)."""
    if "pyre" not in sys.modules:
        stub = types.ModuleType("pyre")
        stub.__path__ = [str(_PYRE_PACKAGE)]
        sys.modules["pyre"] = stub

    spec = importlib.util.spec_from_file_location(
        "pyre.stos_manual_paths",
        _PYRE_PACKAGE / "stos_manual_paths.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["pyre.stos_manual_paths"] = module
    spec.loader.exec_module(module)
    return module


_smp = _load_stos_manual_paths_module()
BrowseMode = _smp.BrowseMode
ensure_manual_directory = _smp.ensure_manual_directory
is_manual_input_directory = _smp.is_manual_input_directory
manual_directory = _smp.manual_directory
parent_stos_group_folder = _smp.parent_stos_group_folder
path_to_manual_transform = _smp.path_to_manual_transform
resolve_default_load_path = _smp.resolve_default_load_path
scan_stos_browser_rows = _smp.scan_stos_browser_rows


class TestManualDirectoryHelpers(unittest.TestCase):
    def test_manual_directory_and_ensure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manual = ensure_manual_directory(tmp)
            self.assertEqual(manual, os.path.join(tmp, "Manual"))
            self.assertTrue(os.path.isdir(manual))

    def test_path_to_manual_transform(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manual = ensure_manual_directory(tmp)
            stos_path = os.path.join(manual, "33-34.stos")
            with open(stos_path, "w", encoding="utf-8") as handle:
                handle.write("x")
            found = path_to_manual_transform(tmp, "33-34.stos")
            self.assertEqual(found, stos_path)
            self.assertIsNone(path_to_manual_transform(tmp, "missing.stos"))

    def test_is_manual_input_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manual = os.path.join(tmp, "Manual")
            os.makedirs(manual)
            self.assertTrue(is_manual_input_directory(manual))
            self.assertFalse(is_manual_input_directory(tmp))

    def test_parent_stos_group_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            group = os.path.join(tmp, "Grid32")
            manual = os.path.join(group, "Manual")
            os.makedirs(manual)
            self.assertEqual(parent_stos_group_folder(manual), group)


class TestResolveDefaultLoadPath(unittest.TestCase):
    def test_prefers_manual(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            auto = os.path.join(tmp, "a.stos")
            manual = os.path.join(tmp, "Manual", "a.stos")
            os.makedirs(os.path.dirname(manual), exist_ok=True)
            open(auto, "w", encoding="utf-8").close()
            open(manual, "w", encoding="utf-8").close()
            self.assertEqual(resolve_default_load_path(auto, manual), manual)

    def test_falls_back_to_auto(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            auto = os.path.join(tmp, "a.stos")
            open(auto, "w", encoding="utf-8").close()
            self.assertEqual(resolve_default_load_path(auto, None), auto)


class TestScanStosBrowserRows(unittest.TestCase):
    def _touch(self, path: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("stub")

    def test_group_mode_merges_auto_and_manual(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self._touch(os.path.join(tmp, "10-11.stos"))
            self._touch(os.path.join(tmp, "Manual", "10-11.stos"))
            self._touch(os.path.join(tmp, "20-21.stos"))
            rows = scan_stos_browser_rows(tmp, BrowseMode.stos_group)
            self.assertEqual(len(rows), 2)
            by_name = {row.basename: row for row in rows}
            merged = by_name["10-11.stos"]
            self.assertTrue(merged.has_manual_override)
            self.assertEqual(merged.default_load_path, merged.manual_path)
            self.assertIsNotNone(by_name["20-21.stos"].auto_path)

    def test_group_mode_manual_only_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self._touch(os.path.join(tmp, "Manual", "05-06.stos"))
            rows = scan_stos_browser_rows(tmp, BrowseMode.stos_group)
            self.assertEqual(len(rows), 1)
            self.assertIsNone(rows[0].auto_path)
            self.assertTrue(rows[0].has_manual_override)

    def test_flat_manual_mode_no_nested_manual(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manual_root = os.path.join(tmp, "Grid32", "Manual")
            self._touch(os.path.join(manual_root, "01-02.stos"))
            os.makedirs(os.path.join(manual_root, "Manual"), exist_ok=True)
            self._touch(os.path.join(manual_root, "Manual", "nested.stos"))
            rows = scan_stos_browser_rows(manual_root, BrowseMode.flat_manual)
            names = {row.basename for row in rows}
            self.assertEqual(names, {"01-02.stos"})
            self.assertIsNone(rows[0].auto_path)

    def test_sort_order_by_section_pair(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self._touch(os.path.join(tmp, "100-101.stos"))
            self._touch(os.path.join(tmp, "02-03.stos"))
            rows = scan_stos_browser_rows(tmp, BrowseMode.stos_group)
            self.assertEqual([row.basename for row in rows], ["02-03.stos", "100-101.stos"])


if __name__ == "__main__":
    unittest.main()
