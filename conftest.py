"""
Pytest hooks and helpers for nornir-pyre.

Headless / Dev Container runs set ``NORNIR_HEADLESS=1`` and omit PyQt6; Qt OpenGL
scratch scripts under ``tests/`` must not be imported during collection (see
``pytest_ignore_collect`` below). Parity with umbrella policy is described in
``docs/docker/cursor_dev.rst``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

__all__ = ["is_headless"]


def is_headless() -> bool:
    """Match ``nornir_imageregistration.headless.is_headless`` (env + Linux DISPLAY)."""
    flag = os.environ.get("NORNIR_HEADLESS", "").strip().lower()
    if flag in ("1", "true", "yes", "on"):
        return True
    if sys.platform != "win32" and not os.environ.get("DISPLAY"):
        return True
    return False


_PYRE_ROOT = Path(__file__).resolve().parent
_TEST_DIR = _PYRE_ROOT / "tests"

# Module names that import PyQt at top level but are not pytest suites.
_IGNORED_TEST_MODULE_NAMES = frozenset(
    {
        "test_enum.py",
        "test_enum2.py",
        "test_qopengl.py",
    }
)


def pytest_ignore_collect(collection_path: Path, config) -> bool | None:  # noqa: ARG001
    """Do not collect Qt/OpenGL driver scripts as test modules (avoids PyQt import in headless)."""
    try:
        resolved = collection_path.resolve()
    except OSError:
        return None
    try:
        resolved.relative_to(_TEST_DIR)
    except ValueError:
        return None

    name = resolved.name
    if name in _IGNORED_TEST_MODULE_NAMES or name.endswith("_qt.py"):
        return True
    # ``test_pure_units`` imports ``pyre.gl_engine``, which pulls in PyQt6 (ShaderVAO). Headless
    # cursor-dev does not install PyQt6; skip collection when the binding is absent.
    if name == "test_pure_units.py":
        import importlib.util

        if importlib.util.find_spec("PyQt6") is None:
            return True
    return None
