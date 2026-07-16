"""
Created on Sep 12, 2013

@author: u0490822
"""
import os
import sys


def _ensure_stdio_streams() -> None:
    """Attach devnull streams when PyInstaller windowed boot leaves stdio as None."""
    if sys.stdin is None:
        sys.stdin = open(os.devnull, "r", encoding="utf-8")
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")


_ensure_stdio_streams()

from pyre.frozen_paths import configure_frozen_environment


def _run_smoke_test() -> int:
    """Verify frozen/runtime imports without starting the GUI."""
    configure_frozen_environment()

    import nornir_buildmanager  # noqa: F401
    import nornir_imageregistration  # noqa: F401
    import nornir_pools  # noqa: F401
    import nornir_shared  # noqa: F401
    import pyre  # noqa: F401

    print("SMOKE_OK")
    return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--smoke-test":
        raise SystemExit(_run_smoke_test())

    import pyre.launcher as launcher

    launcher.Run()


if __name__ == '__main__':
    main()
