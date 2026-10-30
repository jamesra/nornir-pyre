"""Micro-benchmark for TransformController._forget_point_ids (category 18).

Times the real method on a stub controller whose registration queue and busy sync are
no-ops, so only the keep-mask and the id->row map rebuild are measured. Sizes cover a
hand-placed STOS (1k points) up to a dense refine-grid mesh (10k points), dropping one
point (single delete), 16 points (virtual boundary removal), and 10% (box delete).
"""

from __future__ import annotations

import numpy as np
import pyperf
from pyre.controllers.transformcontroller import TransformController


class _NoopQueue:
    """Registration queue stand-in; cancel does nothing."""

    def cancel(self, point_id: int) -> None:
        """Ignore the cancel request."""


class _StubController:
    """Just the state _forget_point_ids reads and writes."""

    _point_ids: np.ndarray
    _id_to_index: dict[int, int]

    _forget_point_ids = TransformController._forget_point_ids
    _rebuild_id_to_index = TransformController._rebuild_id_to_index

    def __init__(self) -> None:
        self._registration_queue = _NoopQueue()
        self._point_ids = np.empty(0, dtype=np.int64)
        self._id_to_index = {}

    def _sync_register_busy(self) -> None:
        """No busy-point bookkeeping in the benchmark."""


def _bench_case(runner: pyperf.Runner, num_points: int, num_drop: int) -> None:
    rng = np.random.default_rng(0)
    ids = np.arange(num_points, dtype=np.int64)
    drop = [int(v) for v in rng.choice(ids, size=num_drop, replace=False)]
    stub = _StubController()

    def worker() -> None:
        stub._point_ids = ids
        stub._forget_point_ids(drop)

    runner.bench_func(f"forget_point_ids_n{num_points}_drop{num_drop}", worker)


def main() -> None:
    runner = pyperf.Runner()
    for num_points, num_drop in ((1000, 1), (1000, 16), (1000, 100), (10000, 1), (10000, 1000)):
        _bench_case(runner, num_points, num_drop)


if __name__ == "__main__":
    main()
