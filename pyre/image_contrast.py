"""Shared Source/Target contrast helpers for display and registration."""

from __future__ import annotations

from typing import cast

import numpy as np
from numpy.typing import NDArray

from dependency_injector.wiring import Provide, inject

import nornir_imageregistration
from nornir_imageregistration.image_stats import (
    ApproximateHistogramOfArray,
    even_histogram_stride,
)
from nornir_shared.histogram import Histogram
from pyre.container import IContainer
from pyre.settings.app import AppSettings, ImageDisplayContrast
from pyre.space import Space

LEVEL_MIN: float = 0.0
LEVEL_MAX: float = 255.0
GAMMA_MIN: float = 0.01
GAMMA_MAX: float = 10.0
_MIN_SPAN: float = 1e-3
# Float mosaics from ImagePermutationHelper are ~[0, 1]; contrast UI/shader use 0–255.
_UNIT_INTERVAL_MAX: float = 1.5

# Re-export for contrast UI callers.
histogram_sample_stride = even_histogram_stride


def _xp_for_image(image: NDArray):
    """Return the array module for *image* (CuPy or NumPy)."""
    try:
        import cupy as cp
        return cp.get_array_module(image)
    except Exception:
        return np


def image_is_unit_interval(image: NDArray) -> bool:
    """True when intensities are normalized ~[0, 1] rather than 0–255 display units."""
    if getattr(image, "size", 0) == 0:
        return False
    if np.issubdtype(np.dtype(getattr(image, "dtype", np.float32)), np.integer):
        return False
    xp = _xp_for_image(image)
    return float(xp.max(image)) <= _UNIT_INTERVAL_MAX


def intensities_in_display_units(image: NDArray) -> NDArray:
    """Return a host copy of *image* scaled to 0–255 contrast/histogram units."""
    host = image.get() if hasattr(image, "get") else np.asarray(image)
    if image_is_unit_interval(image):
        return host.astype(np.float32, copy=False) * float(LEVEL_MAX)
    return host


def approximate_image_histogram(
        image: NDArray,
        *,
        sample_fraction: float = 0.02,
        num_bins: int = 256,
        min_val: float = LEVEL_MIN,
        max_val: float = LEVEL_MAX,
) -> Histogram | None:
    """Build an intensity histogram from an even spatial subsample of *image*."""
    try:
        return ApproximateHistogramOfArray(
            intensities_in_display_units(image),
            sample_fraction=sample_fraction,
            bpp=8,
            num_bins=num_bins,
            min_val=min_val,
            max_val=max_val,
        )
    except ValueError:
        return None


def is_identity_contrast(contrast: ImageDisplayContrast) -> bool:
    """True when contrast leaves 0–255 intensities unchanged."""
    return (
        abs(float(contrast.min) - LEVEL_MIN) < 1e-6
        and abs(float(contrast.max) - LEVEL_MAX) < 1e-6
        and abs(float(contrast.gamma) - 1.0) < 1e-6
    )


def normalize_contrast(
        contrast: ImageDisplayContrast,
        *,
        prefer_max: bool = True,
) -> ImageDisplayContrast:
    """Clamp levels/gamma and ensure min < max without blocking the user.

    When min >= max, nudge the non-preferred side by a small epsilon.
    """
    lo = float(np.clip(float(contrast.min), LEVEL_MIN, LEVEL_MAX))
    hi = float(np.clip(float(contrast.max), LEVEL_MIN, LEVEL_MAX))
    gamma = float(np.clip(float(contrast.gamma), GAMMA_MIN, GAMMA_MAX))
    if lo >= hi:
        if prefer_max:
            lo = max(LEVEL_MIN, hi - _MIN_SPAN)
            if lo >= hi:
                hi = min(LEVEL_MAX, lo + _MIN_SPAN)
        else:
            hi = min(LEVEL_MAX, lo + _MIN_SPAN)
            if lo >= hi:
                lo = max(LEVEL_MIN, hi - _MIN_SPAN)
    return ImageDisplayContrast(min=lo, max=hi, gamma=gamma)


def apply_contrast_array(
        image: NDArray,
        contrast: ImageDisplayContrast,
        *,
        copy_on_identity: bool = False,
) -> NDArray:
    """Apply min/max/gamma remap matching TextureShader fragment math.

    Contrast min/max/gamma are 0–255 display units (same as the GL shader).
    Registration mosaics are often float ~[0, 1]; those are scaled into display
    units for the remap, then scaled back so output stays in the input range.
    """
    c = normalize_contrast(contrast)
    if is_identity_contrast(c):
        if copy_on_identity:
            return np.asarray(image).copy() if not hasattr(image, 'get') else image.copy()
        return image

    xp = _xp_for_image(image)
    arr = xp.asarray(image, dtype=xp.float32)
    unit_interval = image_is_unit_interval(image)
    intensity = arr * float(LEVEL_MAX) if unit_interval else arr
    span = max(float(c.max) - float(c.min), _MIN_SPAN)
    norm = xp.clip((intensity - float(c.min)) / span, 0.0, 1.0)
    inv_gamma = 1.0 / float(c.gamma)
    mapped = xp.power(norm, inv_gamma)
    out = mapped if unit_interval else mapped * float(LEVEL_MAX)
    return out.astype(arr.dtype, copy=False)


@inject
def contrast_for_space(
        space: Space,
        settings: AppSettings = Provide[IContainer.settings],
) -> ImageDisplayContrast:
    """Return normalized contrast for Source or Target from AppSettings."""
    if space == Space.Target:
        return normalize_contrast(settings.ui.target_contrast)
    return normalize_contrast(settings.ui.source_contrast)


def set_contrast_for_space(
        space: Space,
        contrast: ImageDisplayContrast,
        settings: AppSettings,
) -> ImageDisplayContrast:
    """Write normalized contrast into settings for *space*; return stored value."""
    normalized = normalize_contrast(contrast)
    if space == Space.Target:
        settings.ui.target_contrast = normalized
    else:
        settings.ui.source_contrast = normalized
    return normalized


def reset_contrast_for_space(space: Space, settings: AppSettings) -> ImageDisplayContrast:
    """Restore identity contrast for *space*."""
    return set_contrast_for_space(space, ImageDisplayContrast(), settings)


class ContrastedImagePermutationHelper:
    """Wrap an ImagePermutationHelper applying contrast to registration pixels."""

    _inner: nornir_imageregistration.ImagePermutationHelper
    _contrast: ImageDisplayContrast
    _cached: NDArray | None
    _stats: object | None

    def __init__(
            self,
            inner: nornir_imageregistration.ImagePermutationHelper,
            contrast: ImageDisplayContrast,
    ) -> None:
        self._inner = inner
        self._contrast = normalize_contrast(contrast)
        self._cached = None
        self._stats = None

    @property
    def shape(self) -> tuple[int, int]:
        return self._inner.shape

    @property
    def Image(self) -> NDArray:
        return self._inner.Image

    @property
    def Mask(self) -> NDArray | None:
        return self._inner.Mask

    @property
    def BlendedMask(self) -> NDArray:
        return self._inner.BlendedMask

    @property
    def Stats(self):
        if self._stats is None:
            contrasted = self.ImageWithMaskAsNoise
            mask = self._inner.BlendedMask
            if mask is not None:
                self._stats = nornir_imageregistration.ImageStats.Create(contrasted[mask])
            else:
                self._stats = nornir_imageregistration.ImageStats.Create(contrasted)
        return self._stats

    @property
    def ImageWithMaskAsNoise(self) -> NDArray:
        if self._cached is None:
            self._cached = apply_contrast_array(
                self._inner.ImageWithMaskAsNoise,
                self._contrast,
                copy_on_identity=True,
            )
        return self._cached


def contrasted_permutation_helper(
        helper: nornir_imageregistration.ImagePermutationHelper,
        contrast: ImageDisplayContrast,
) -> nornir_imageregistration.ImagePermutationHelper:
    """Return *helper* unchanged for identity contrast; otherwise a contrasted wrap.

    The wrapper duck-types :class:`ImagePermutationHelper` for registration entry points.
    """
    c = normalize_contrast(contrast)
    if is_identity_contrast(c):
        return helper
    return cast(
        nornir_imageregistration.ImagePermutationHelper,
        ContrastedImagePermutationHelper(helper, c),
    )
