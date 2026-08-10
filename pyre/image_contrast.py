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

# Re-export for contrast UI callers.
histogram_sample_stride = even_histogram_stride


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
            image,
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

    ``out = pow(clamp((x - min) / (max - min), 0, 1), 1/gamma) * 255``
    so registration arrays stay in the same 0–255-ish units as display textures.
    """
    c = normalize_contrast(contrast)
    if is_identity_contrast(c):
        if copy_on_identity:
            return np.asarray(image).copy() if not hasattr(image, 'get') else image.copy()
        return image

    try:
        import cupy as cp
        xp = cp.get_array_module(image)
    except Exception:
        xp = np

    arr = xp.asarray(image, dtype=xp.float32)
    span = max(float(c.max) - float(c.min), _MIN_SPAN)
    norm = xp.clip((arr - float(c.min)) / span, 0.0, 1.0)
    inv_gamma = 1.0 / float(c.gamma)
    out = xp.power(norm, inv_gamma) * float(LEVEL_MAX)
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

    def __init__(
            self,
            inner: nornir_imageregistration.ImagePermutationHelper,
            contrast: ImageDisplayContrast,
    ) -> None:
        self._inner = inner
        self._contrast = normalize_contrast(contrast)
        self._cached = None

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
        return self._inner.Stats

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
