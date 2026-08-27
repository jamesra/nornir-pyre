"""Tests for help text anchor and section extraction (no PyQt import)."""

from __future__ import annotations

import importlib.util
import os
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
    def test_repository_readme_contains_anchor(self) -> None:
        rst_path = _PYRE_ROOT / "README.rst"
        if not rst_path.is_file():
            self.skipTest("README.rst not present in development tree")
        text = readme_text_with_fallback()
        self.assertIn(CONTROLS_HELP_ANCHOR, text)
        self.assertGreater(controls_help_anchor_index(text), 0)
        section = controls_help_section(text)
        self.assertIsNotNone(section)
        assert section is not None
        self.assertIn("Keyboard Controls", section)
        self.assertIn("Grid:", section)
        self.assertIn("Refine w/ Grid", section)


if __name__ == "__main__":
    unittest.main()
