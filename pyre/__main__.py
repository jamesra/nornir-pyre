"""
Created on Sep 12, 2013

@author: u0490822
"""
import sys

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
