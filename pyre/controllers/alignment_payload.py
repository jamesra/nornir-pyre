"""Host shared-memory staging for control-point alignment payloads.

``AttemptAlignPoint`` receives the full image pair and crops the alignment ROI
itself, so dispatching one control point per pool task would pickle both whole
images per point. Staging copies the pair into ``multiprocessing.shared_memory``
once per "register all" batch and passes only segment names to workers, which
attach and crop.

Alignment math is host-only (``use_gpu=False``) and pool workers force a numpy
backend (``ConfigureForkPoolWorker``), so a CuPy Pyre session still stages to
host memory here rather than being confined to the in-process thread pool.
CUDA IPC is Linux-only, so sharing device buffers with workers is not an option.
"""

from __future__ import annotations

import logging
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from multiprocessing import shared_memory
from typing import Iterator

import numpy as np
from numpy.typing import NDArray

import nornir_imageregistration
from nornir_imageregistration.image_permutation_helper import ImagePermutationHelper

_logger = logging.getLogger(__name__)


def shared_memory_supported() -> bool:
    """True when ``multiprocessing.shared_memory`` can back an alignment payload."""
    return hasattr(shared_memory, 'SharedMemory')


@dataclass(frozen=True)
class SharedArrayRef:
    """Picklable description of one host array residing in a shared segment."""

    name: str
    shape: tuple[int, ...]
    dtype: str

    @contextmanager
    def attach(self) -> Iterator[NDArray]:
        """Map the segment read-only for the duration of the block."""
        shm = shared_memory.SharedMemory(name=self.name)
        view: NDArray | None = None
        try:
            view = np.ndarray(self.shape, dtype=np.dtype(self.dtype), buffer=shm.buf)
            view.flags.writeable = False
            yield view
        finally:
            # The view exports the segment's buffer; it must be released before
            # close() or SharedMemory raises BufferError.
            del view
            shm.close()


@dataclass(frozen=True)
class SharedImageRef:
    """Picklable handle to one staged image: noise-filled pixels, mask, and stats."""

    image: SharedArrayRef
    mask: SharedArrayRef
    median: float
    mean: float
    std: float
    min: float
    max: float

    def build_stats(self) -> nornir_imageregistration.ImageStats:
        """Rebuild an :class:`ImageStats` from the staged scalars."""
        stats = nornir_imageregistration.ImageStats()
        stats.median = self.median
        stats.mean = self.mean
        stats.std = self.std
        stats.min = self.min
        stats.max = self.max
        return stats

    @contextmanager
    def attach(self) -> Iterator[tuple[NDArray, NDArray, nornir_imageregistration.ImageStats]]:
        """Map the image and mask segments and yield them with rebuilt stats."""
        with self.image.attach() as image, self.mask.attach() as mask:
            yield image, mask, self.build_stats()


@dataclass(frozen=True)
class SharedImagePairRef:
    """Picklable handle to a staged source/target pair for one alignment batch."""

    source: SharedImageRef
    target: SharedImageRef


@dataclass(frozen=True)
class HostImagePayload:
    """Host copies of the arrays alignment consumes, plus scalar stats.

    Built on the thread that owns the arrays (the CUDA-owning thread for a CuPy
    session) so the shared-memory copy itself can run on a worker thread.
    """

    pixels: NDArray
    mask: NDArray
    median: float
    mean: float
    std: float
    min: float
    max: float


def host_image_payload(image: ImagePermutationHelper) -> HostImagePayload:
    """Host-copy the noise-filled image, blended mask, and stats of *image*."""
    stats = image.Stats
    return HostImagePayload(
        pixels=np.ascontiguousarray(
            nornir_imageregistration.EnsureNumpyArray(image.ImageWithMaskAsNoise)),
        mask=np.ascontiguousarray(
            nornir_imageregistration.EnsureNumpyArray(image.BlendedMask)),
        median=float(stats.median),
        mean=float(stats.mean),
        std=float(stats.std),
        min=float(stats.min),
        max=float(stats.max),
    )


class StagedImage:
    """Owns the shared segments holding one side of an alignment pair.

    Reference counted: :meth:`close` only unlinks once every in-flight job that
    was handed this generation has released it. Unlinking a segment that a
    worker still has mapped fails on Windows and faults on POSIX.
    """

    _ref: SharedImageRef
    _segments: list[shared_memory.SharedMemory]
    _refcount: int
    _close_requested: bool
    _released: bool

    def __init__(self, ref: SharedImageRef,
                 segments: list[shared_memory.SharedMemory]) -> None:
        self._ref = ref
        self._segments = segments
        self._refcount = 0
        self._close_requested = False
        self._released = False

    @property
    def ref(self) -> SharedImageRef:
        """Picklable handle to pass to pool workers."""
        return self._ref

    @property
    def in_flight_count(self) -> int:
        """Number of jobs still holding this generation."""
        return self._refcount

    @property
    def released(self) -> bool:
        """True once the segments have been unlinked."""
        return self._released

    def retain(self) -> None:
        """Record that one more job may attach to these segments."""
        self._refcount += 1

    def release(self) -> None:
        """Drop one job's hold, unlinking when a close was already requested."""
        if self._refcount > 0:
            self._refcount -= 1
        if self._close_requested:
            self.close()

    def close(self) -> None:
        """Unlink the segments once no job holds them. Safe to call repeatedly."""
        self._close_requested = True
        if self._released or self._refcount > 0:
            return
        self._released = True
        for segment in self._segments:
            try:
                segment.close()
                segment.unlink()
            except FileNotFoundError:
                pass
            except Exception:
                _logger.exception("Could not release alignment payload segment %s",
                                  segment.name)
        self._segments = []


def stage_host_image(payload: HostImagePayload) -> StagedImage | None:
    """Copy an already host-resident payload into fresh shared segments."""
    if not shared_memory_supported():
        return None
    with ExitStack() as stack:
        try:
            image_ref, image_segment = _stage_array(payload.pixels, stack)
            mask_ref, mask_segment = _stage_array(payload.mask, stack)
        except Exception:
            _logger.exception("Could not publish alignment image in shared memory")
            return None
        stack.pop_all()
    ref = SharedImageRef(
        image=image_ref,
        mask=mask_ref,
        median=payload.median,
        mean=payload.mean,
        std=payload.std,
        min=payload.min,
        max=payload.max,
    )
    return StagedImage(ref, [image_segment, mask_segment])


class StagedImagePair:
    """Owns the shared segments for one source/target pair.

    Must stay referenced in the parent while alignments are in flight: a segment
    is released once its last handle closes, and on Windows there is no
    filesystem entry keeping it alive between processes.
    """

    _ref: SharedImagePairRef
    _segments: list[shared_memory.SharedMemory]
    _source_key: int
    _target_key: int
    _closed: bool

    def __init__(self,
                 ref: SharedImagePairRef,
                 segments: list[shared_memory.SharedMemory],
                 source_key: int,
                 target_key: int) -> None:
        self._ref = ref
        self._segments = segments
        self._source_key = source_key
        self._target_key = target_key
        self._closed = False

    @property
    def ref(self) -> SharedImagePairRef:
        """Picklable handle to pass to pool workers."""
        return self._ref

    def matches(self,
                source_image: ImagePermutationHelper,
                target_image: ImagePermutationHelper) -> bool:
        """True when this staging was built from these same helper objects."""
        return (not self._closed
                and self._source_key == id(source_image)
                and self._target_key == id(target_image))

    def close(self) -> None:
        """Release the segments. Safe to call more than once."""
        if self._closed:
            return
        self._closed = True
        for segment in self._segments:
            try:
                segment.close()
                segment.unlink()
            except FileNotFoundError:
                pass
            except Exception:
                _logger.exception("Could not release alignment payload segment %s",
                                  segment.name)
        self._segments = []


def _stage_array(arr: NDArray, stack: ExitStack) -> tuple[SharedArrayRef, shared_memory.SharedMemory]:
    """Copy *arr* to host memory in a new shared segment registered on *stack*."""
    host = np.ascontiguousarray(nornir_imageregistration.EnsureNumpyArray(arr))
    if host.nbytes == 0:
        raise ValueError("Cannot stage an empty array in shared memory")
    segment = shared_memory.SharedMemory(create=True, size=host.nbytes)
    stack.callback(segment.unlink)
    stack.callback(segment.close)
    view = np.ndarray(host.shape, dtype=host.dtype, buffer=segment.buf)
    view[:] = host
    return SharedArrayRef(segment.name, tuple(host.shape), host.dtype.str), segment


def _stage_image(image: ImagePermutationHelper,
                 stack: ExitStack) -> tuple[SharedImageRef, list[shared_memory.SharedMemory]]:
    """Stage the noise-filled image and blended mask that alignment consumes."""
    image_ref, image_segment = _stage_array(image.ImageWithMaskAsNoise, stack)
    mask_ref, mask_segment = _stage_array(image.BlendedMask, stack)
    stats = image.Stats
    ref = SharedImageRef(
        image=image_ref,
        mask=mask_ref,
        median=float(stats.median),
        mean=float(stats.mean),
        std=float(stats.std),
        min=float(stats.min),
        max=float(stats.max),
    )
    return ref, [image_segment, mask_segment]


def stage_image_pair(source_image: ImagePermutationHelper,
                     target_image: ImagePermutationHelper) -> StagedImagePair | None:
    """Copy an image pair into shared memory, or return None when staging fails.

    Returning None is the signal to fall back to the in-process thread pool.
    """
    if not shared_memory_supported():
        return None
    # ExitStack unwinds every segment created so far if a later one fails, so a
    # partial staging cannot leak segments the parent no longer tracks.
    with ExitStack() as stack:
        try:
            source_ref, source_segments = _stage_image(source_image, stack)
            target_ref, target_segments = _stage_image(target_image, stack)
        except Exception:
            _logger.exception("Could not stage alignment payload in shared memory")
            return None
        stack.pop_all()
    return StagedImagePair(
        SharedImagePairRef(source=source_ref, target=target_ref),
        source_segments + target_segments,
        id(source_image),
        id(target_image),
    )
