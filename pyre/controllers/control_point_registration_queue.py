"""FIFO control-point registration queue keyed by session-stable point IDs."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable

REGISTER_BUSY_REASON = "register"


class ControlPointBusySet:
    """Union of session IDs marked busy for any named work-queue reason."""

    _reasons: dict[str, set[int]]

    def __init__(self) -> None:
        self._reasons = {}

    @property
    def ids(self) -> frozenset[int]:
        """Session IDs present in any reason bucket."""
        union: set[int] = set()
        for bucket in self._reasons.values():
            union.update(bucket)
        return frozenset(union)

    def mark(self, reason: str, ids: Iterable[int]) -> bool:
        """Add *ids* under *reason*. Returns True when the union changed."""
        before = self.ids
        bucket = self._reasons.setdefault(reason, set())
        bucket.update(int(point_id) for point_id in ids)
        return before != self.ids

    def unmark(self, reason: str, ids: Iterable[int]) -> bool:
        """Remove *ids* from *reason*. Returns True when the union changed."""
        before = self.ids
        bucket = self._reasons.get(reason)
        if bucket is None:
            return False
        for point_id in ids:
            bucket.discard(int(point_id))
        if not bucket:
            del self._reasons[reason]
        return before != self.ids

    def clear(self, reason: str) -> bool:
        """Drop every ID for *reason*. Returns True when the union changed."""
        before = self.ids
        if reason not in self._reasons:
            return False
        del self._reasons[reason]
        return before != self.ids

    def set_ids(self, reason: str, ids: Iterable[int]) -> bool:
        """Replace *reason* with *ids*. Returns True when the union changed."""
        before = self.ids
        replacement = {int(point_id) for point_id in ids}
        if replacement:
            self._reasons[reason] = replacement
        else:
            self._reasons.pop(reason, None)
        return before != self.ids


class ControlPointRegistrationQueue:
    """Deduped FIFO of point IDs with at most one in-flight job."""

    _pending: deque[int]
    _pending_set: set[int]
    _in_flight: int | None
    _cancelled: set[int]

    def __init__(self) -> None:
        self._pending = deque()
        self._pending_set = set()
        self._in_flight = None
        self._cancelled = set()

    @property
    def in_flight_id(self) -> int | None:
        """ID of the alignment currently running, if any."""
        return self._in_flight

    @property
    def queued_ids(self) -> frozenset[int]:
        """Pending and in-flight IDs (cancelled pending IDs are omitted)."""
        ids = set(self._pending_set)
        if self._in_flight is not None:
            ids.add(self._in_flight)
        return frozenset(ids)

    @property
    def is_idle(self) -> bool:
        """True when nothing is pending or in flight."""
        return self._in_flight is None and not self._pending_set

    def contains(self, point_id: int) -> bool:
        """True when *point_id* is pending or in flight."""
        return point_id in self._pending_set or point_id == self._in_flight

    def enqueue(self, point_ids: Iterable[int]) -> list[int]:
        """Append new IDs. Already pending or in-flight IDs are ignored."""
        added: list[int] = []
        for point_id in point_ids:
            if self.contains(point_id):
                continue
            self._cancelled.discard(point_id)
            self._pending.append(point_id)
            self._pending_set.add(point_id)
            added.append(point_id)
        return added

    def cancel(self, point_id: int) -> None:
        """Drop a pending ID or mark an in-flight job so its result is discarded."""
        if point_id in self._pending_set:
            self._pending_set.discard(point_id)
        if self._in_flight == point_id:
            self._cancelled.add(point_id)

    def cancel_all(self) -> None:
        """Clear pending work and discard the in-flight result when it arrives."""
        if self._in_flight is not None:
            self._cancelled.add(self._in_flight)
        self._pending.clear()
        self._pending_set.clear()

    def is_cancelled(self, point_id: int) -> bool:
        """True when the in-flight job for *point_id* must discard its result."""
        return point_id in self._cancelled

    def take_next(self) -> int | None:
        """Pop the next non-cancelled pending ID and mark it in flight."""
        while self._pending:
            point_id = self._pending.popleft()
            if point_id not in self._pending_set:
                continue
            self._pending_set.discard(point_id)
            self._in_flight = point_id
            return point_id
        return None

    def finish(self, point_id: int) -> None:
        """Clear in-flight state after a job completes or is skipped."""
        if self._in_flight == point_id:
            self._in_flight = None
        self._cancelled.discard(point_id)
