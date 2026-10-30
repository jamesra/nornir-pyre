"""Behavior of TransformController._forget_point_ids (session ID removal after a delete)."""

from __future__ import annotations

import unittest

import numpy as np
from hypothesis import example, given, settings
from hypothesis import strategies as st
from pyre.controllers.transformcontroller import TransformController

_INT64 = st.integers(min_value=np.iinfo(np.int64).min, max_value=np.iinfo(np.int64).max)


class _RecordingQueue:
    """Registration queue stand-in that records cancelled session IDs."""

    cancelled: list[int]

    def __init__(self) -> None:
        self.cancelled = []

    def cancel(self, point_id: int) -> None:
        """Record *point_id* as cancelled."""
        self.cancelled.append(point_id)


class _StubController:
    """Just the state _forget_point_ids reads and writes, without Qt or a transform."""

    _point_ids: np.ndarray
    _id_to_index: dict[int, int]
    _registration_queue: _RecordingQueue
    sync_calls: int

    _forget_point_ids = TransformController._forget_point_ids
    _rebuild_id_to_index = TransformController._rebuild_id_to_index

    def __init__(self, point_ids: list[int]) -> None:
        self._point_ids = np.asarray(point_ids, dtype=np.int64)
        self._id_to_index = {}
        self._registration_queue = _RecordingQueue()
        self.sync_calls = 0

    def _sync_register_busy(self) -> None:
        """Count busy-point syncs."""
        self.sync_calls += 1


class TestForgetPointIds(unittest.TestCase):
    """_forget_point_ids keeps order, drops every listed ID, and rebuilds the row map."""

    @settings(max_examples=300, deadline=None)
    @given(
        point_ids=st.lists(_INT64 | st.integers(min_value=0, max_value=20), max_size=40),
        drop=st.lists(_INT64 | st.integers(min_value=0, max_value=20), max_size=20),
    )
    @example(point_ids=[], drop=[])
    @example(point_ids=[0, 1, 2], drop=[])
    @example(point_ids=[0, 1, 2], drop=[7, 8])
    @example(point_ids=[3, 1, 3, 2], drop=[3, 3])
    @example(point_ids=[0, 1, 2, 3], drop=[0, 1, 2, 3])
    def test_matches_reference(self, point_ids: list[int], drop: list[int]) -> None:
        stub = _StubController(point_ids)
        stub._id_to_index = {-999: -999}
        drop_set = set(drop)
        expected_ids = [pid for pid in point_ids if pid not in drop_set]

        stub._forget_point_ids(drop)

        self.assertEqual(stub._point_ids.dtype, np.int64)
        self.assertEqual(stub._point_ids.tolist(), expected_ids)
        self.assertEqual(sorted(stub._registration_queue.cancelled), sorted(drop_set))
        self.assertEqual(stub.sync_calls, 1 if drop_set else 0)
        if drop_set:
            self.assertEqual(stub._id_to_index, {pid: row for row, pid in enumerate(expected_ids)})
        else:
            self.assertEqual(stub._id_to_index, {-999: -999})


if __name__ == "__main__":
    unittest.main()
