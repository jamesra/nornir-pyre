"""Optional timing helpers for interactive transform display profiling."""

from __future__ import annotations

import os
import time
from contextlib import contextmanager
from typing import Iterator

_ENABLED = os.environ.get('PYRE_PERF_DEBUG', '').strip() not in ('', '0', 'false', 'False')


def enabled() -> bool:
    return _ENABLED


@contextmanager
def timed(label: str) -> Iterator[None]:
    if not _ENABLED:
        yield
        return
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        print(f'[pyre-perf] {label}: {elapsed_ms:.2f} ms')
