"""The nornir-pyre root ``conftest.py`` exports ``is_headless`` without importing the imaging stack."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_CONFTEST_PATH = Path(__file__).resolve().parents[1] / "conftest.py"


def test_conftest_reexports_shared_is_headless_without_heavy_imports() -> None:
    """Pytest loads conftest at startup, before any test asks for matplotlib, CuPy, or Qt.

    Runs in a subprocess because this session has usually imported those already.
    """
    code = (
        "import importlib.util, sys\n"
        "import nornir_shared.headless as shared\n"
        f"spec = importlib.util.spec_from_file_location('_pyre_root_conftest', {str(_CONFTEST_PATH)!r})\n"
        "module = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(module)\n"
        "assert module.is_headless is shared.is_headless\n"
        "assert 'is_headless' in module.__all__\n"
        "heavy = ('matplotlib', 'cupy', 'nornir_imageregistration', 'PyQt6')\n"
        "print(','.join(m for m in heavy if m in sys.modules))\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert result.stdout.strip() == ""
