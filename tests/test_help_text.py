"""Tests for help text anchor and section extraction (no PyQt import)."""

from __future__ import annotations

import importlib.util
import os
import re
import sys
import types
import unittest
from pathlib import Path

_PYRE_ROOT = Path(__file__).resolve().parents[1]
_PYRE_PACKAGE = _PYRE_ROOT / "pyre"


def _load_resource_paths_module():
    """Load resource_paths without importing pyre package __init__ (Qt/OpenGL)."""
    if "pyre" not in sys.modules:
        stub = types.ModuleType("pyre")
        stub.__path__ = [str(_PYRE_PACKAGE)]
        sys.modules["pyre"] = stub

    spec = importlib.util.spec_from_file_location(
        "pyre.resource_paths",
        _PYRE_PACKAGE / "resource_paths.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["pyre.resource_paths"] = module
    spec.loader.exec_module(module)
    return module


_rp = _load_resource_paths_module()
CONTROLS_HELP_ANCHOR = _rp.CONTROLS_HELP_ANCHOR
controls_help_anchor_index = _rp.controls_help_anchor_index
controls_help_section = _rp.controls_help_section
readme_text_with_fallback = _rp.readme_text_with_fallback


_SAMPLE_HELP = """\
Pyre

Usage

Mouse Controls
--------------

Left Button:
    * Click to select

Keyboard Controls
-----------------

Navigation:
    * A, W, S, D: Move the view

Troubleshooting
---------------

OpenGL Issues
"""


class TestControlsHelpAnchorIndex(unittest.TestCase):
    def test_finds_mouse_controls_line(self) -> None:
        self.assertGreater(controls_help_anchor_index(_SAMPLE_HELP), 0)

    def test_missing_anchor_returns_zero(self) -> None:
        self.assertEqual(controls_help_anchor_index("no controls here"), 0)


class TestControlsHelpSection(unittest.TestCase):
    def test_extracts_mouse_through_keyboard_blocks(self) -> None:
        section = controls_help_section(_SAMPLE_HELP)
        self.assertIsNotNone(section)
        assert section is not None
        self.assertIn("Mouse Controls", section)
        self.assertIn("Keyboard Controls", section)
        self.assertIn("Left Button:", section)
        self.assertIn("Navigation:", section)
        self.assertNotIn("Troubleshooting", section)

    def test_missing_section_returns_none(self) -> None:
        self.assertIsNone(controls_help_section("Installation only"))


class TestBundledReadmeSnippet(unittest.TestCase):
    def test_packaged_help_contains_anchor(self) -> None:
        """In-app Help uses pyre/README.txt; the short root README.rst only links to monodoc."""
        txt_path = _PYRE_PACKAGE / "README.txt"
        if not txt_path.is_file():
            self.skipTest("pyre/README.txt not present in development tree")
        text = readme_text_with_fallback()
        self.assertIn(CONTROLS_HELP_ANCHOR, text)
        self.assertGreater(controls_help_anchor_index(text), 0)
        section = controls_help_section(text)
        self.assertIsNotNone(section)
        assert section is not None
        self.assertIn("Keyboard Controls", section)
        self.assertIn("Grid:", section)
        self.assertIn("Refine w/ Grid", section)


def _menu_label(raw: str) -> str:
    """Menu text as shown: no mnemonic '&', shortcut column ('\\t...') or trailing ellipsis."""
    label = raw.split("\\t")[0].replace("&", "")
    for ellipsis in ("…", "\\u2026", "..."):
        label = label.removesuffix(ellipsis)
    return label.strip()


class TestHelpMenuPaths(unittest.TestCase):
    """Every "Menu → Item" the help text names must exist in the STOS window menus."""

    def test_menu_paths_in_help_exist(self) -> None:
        source = (_PYRE_PACKAGE / "ui" / "windows" / "stoswindow.py").read_text(encoding="utf-8")
        top_level = {_menu_label(m) for m in re.findall(r'QMenu\("([^"]+)", self\)', source)}
        items = {_menu_label(m) for m in re.findall(
            r'(?:addAction|addMenu|QAction)\(\s*"([^"]+)"', source)}
        self.assertIn("Help", top_level)

        help_text = (_PYRE_PACKAGE / "README.txt").read_text(encoding="utf-8")
        paths = re.findall(r"(\w+) → (.+)", help_text)
        self.assertTrue(paths, "help text should point at menu entries")
        for menu, rest in paths:
            with self.subTest(path=f"{menu} → {rest}"):
                self.assertIn(menu, top_level)
                # The prose after the arrow must start with a real item label.
                self.assertTrue(
                    any(re.match(re.escape(item) + r"(?!\w)", rest) for item in items),
                    f"no menu item starts {rest!r}")


if __name__ == "__main__":
    unittest.main()
