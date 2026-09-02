"""Generation-tracked shared-memory publications of the alignment image pair.

Control-point alignment scores the whole source/target mosaic pair, so the
pixels are published to shared memory once when STOS images are loaded (or
contrast settles) rather than per Spacebar. Each publication is a *generation*:
loading another image bumps the generation and marks that side not ready, and
the registration pump waits until both sides are ready again.

Old generations are reference counted. A generation is unlinked only after every
job that was handed its segment names has finished, because unlinking a mapped
segment fails on Windows and faults on POSIX.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from pyre.controllers.alignment_payload import (
    SharedImagePairRef,
    StagedImage,
)
from pyre.space import Space

_logger = logging.getLogger(__name__)


@dataclass
class _Publication:
    """One side's newest publication attempt."""

    generation: int
    helper_key: int
    staged: StagedImage | None = None
    ready: bool = False
    failed: bool = False


class PublishedPairLease:
    """Holds both sides of a published generation for the life of one job."""

    _ref: SharedImagePairRef
    _held: tuple[StagedImage, StagedImage]
    _released: bool

    def __init__(self, ref: SharedImagePairRef,
                 held: tuple[StagedImage, StagedImage]) -> None:
        self._ref = ref
        self._held = held
        self._released = False
        for staged in held:
            staged.retain()

    @property
    def ref(self) -> SharedImagePairRef:
        """Picklable handle to pass to a pool worker."""
        return self._ref

    def release(self) -> None:
        """Drop this job's hold on both generations. Safe to call repeatedly."""
        if self._released:
            return
        self._released = True
        for staged in self._held:
            staged.release()


class RegistrationImageStore:
    """Per-side published alignment images with generation and refcount tracking."""

    _publications: dict[Space, _Publication]
    _next_generation: int

    def __init__(self) -> None:
        self._publications = {}
        self._next_generation = 0

    @staticmethod
    def _helper_key(helper: object | None) -> int:
        return 0 if helper is None else id(helper)

    def begin(self, space: Space, helper: object) -> int:
        """Start a publication for *space* and return its generation.

        Retires the previous generation for that side; its segments survive
        until the last job holding them finishes.
        """
        previous = self._publications.get(space)
        if previous is not None and previous.staged is not None:
            previous.staged.close()
        self._next_generation += 1
        generation = self._next_generation
        self._publications[space] = _Publication(
            generation=generation, helper_key=self._helper_key(helper))
        return generation

    def complete(self, space: Space, generation: int,
                 staged: StagedImage | None) -> bool:
        """Install a finished publication. False when *generation* is stale."""
        current = self._publications.get(space)
        if current is None or current.generation != generation:
            if staged is not None:
                # Another image was loaded while this copy ran.
                staged.close()
            _logger.info("Discarding stale alignment image publication gen=%s", generation)
            return False
        current.staged = staged
        current.ready = staged is not None
        current.failed = staged is None
        return True

    def generation(self, space: Space) -> int | None:
        """Current generation for *space*, or None when nothing was published."""
        current = self._publications.get(space)
        return None if current is None else current.generation

    def is_ready(self, space: Space) -> bool:
        """True when *space* has a mapped, current publication."""
        current = self._publications.get(space)
        return current is not None and current.ready

    def publish_pending(self) -> bool:
        """True while any side's newest publication is still being copied."""
        return any(not entry.ready and not entry.failed
                   for entry in self._publications.values())

    def lease(self, source_helper: object,
              target_helper: object) -> PublishedPairLease | None:
        """Lease the published pair when both sides match *source*/*target*.

        Returns None when either side is unpublished, still copying, failed, or
        was published from a different helper object.
        """
        held: list[StagedImage] = []
        for space, helper in ((Space.Source, source_helper), (Space.Target, target_helper)):
            entry = self._publications.get(space)
            if (entry is None
                    or not entry.ready
                    or entry.staged is None
                    or entry.staged.released
                    or entry.helper_key != self._helper_key(helper)):
                return None
            held.append(entry.staged)
        ref = SharedImagePairRef(source=held[0].ref, target=held[1].ref)
        return PublishedPairLease(ref, (held[0], held[1]))

    def retire(self, space: Space) -> None:
        """Retire only *space*; its segments unlink as in-flight jobs finish."""
        entry = self._publications.pop(space, None)
        if entry is not None and entry.staged is not None:
            entry.staged.close()

    def invalidate(self) -> None:
        """Retire every publication; segments unlink as in-flight jobs finish."""
        for entry in self._publications.values():
            if entry.staged is not None:
                entry.staged.close()
        self._publications = {}

    def in_flight_holds(self) -> int:
        """Total number of job holds outstanding across published sides."""
        return sum(entry.staged.in_flight_count
                   for entry in self._publications.values()
                   if entry.staged is not None)
