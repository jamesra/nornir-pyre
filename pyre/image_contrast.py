"""Shared Source/Target contrast helpers for display and registration."""

from __future__ import annotations

import copy
import logging
import os
from typing import cast

import nornir_imageregistration
import numpy as np
from dependency_injector.wiring import Provide, inject
from nornir_imageregistration.image_stats import (
    ApproximateHistogramOfArray,
    even_histogram_stride,
)
from nornir_shared.histogram import Histogram
from numpy.typing import NDArray
from PIL import Image

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
# Fraction of samples clipped at each end by Auto contrast (Contrast Adjustment "Auto" button).
AUTO_MIN_PERCENTILE: float = 0.005
AUTO_MAX_PERCENTILE: float = 0.005
# Auto gamma limits and how close the median may sit to min/max, as in Viking's CrushInfo.AutoGamma.
AUTO_GAMMA_MIN: float = 0.25
AUTO_GAMMA_MAX: float = 4.0
_AUTO_GAMMA_EDGE: float = 0.02
# PNG text chunk the Nornir importer writes into noise-crushed (Quantized) tiles and images.
_CRUSH_PNG_CHUNK: str = "nornir_crush"

logger = logging.getLogger(__name__)

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


def auto_gamma(hist: Histogram | None, lo: float, hi: float) -> float:
    """The gamma that shows the median pixel between *lo* and *hi* at mid grey (Viking's Auto gamma).

    Display maps ``t ** (1 / gamma)``, so a median at fraction ``t`` of the window needs
    ``gamma = log(t) / log(0.5)``. Bin 0 is skipped: masked and empty borders put most pixels there.
    1 (linear) without a histogram or when no pixel lies inside the window.
    """
    if hist is None or not hi > lo:
        return 1.0
    inside = [(hist.BinRepresentativeValue(i), count) for i, count in enumerate(hist.Bins)
              if i > 0 and count > 0 and lo <= hist.BinRepresentativeValue(i) <= hi]
    total = sum(count for _, count in inside)
    if total <= 0:
        return 1.0
    running = 0.0
    median = inside[-1][0]
    for value, count in inside:
        running += count
        if running * 2 >= total:
            median = value
            break
    t = float(np.clip((median - lo) / (hi - lo), _AUTO_GAMMA_EDGE, 1.0 - _AUTO_GAMMA_EDGE))
    return float(np.clip(np.log(t) / np.log(0.5), AUTO_GAMMA_MIN, AUTO_GAMMA_MAX))


def auto_contrast(image: NDArray) -> ImageDisplayContrast | None:
    """The Contrast Adjustment "Auto" setting: min/max from histogram percentiles, gamma locked to Auto.

    Bin 0 is left out, as in :func:`auto_gamma` and Viking: masked and empty borders put most pixels
    there (about 17% on RC3), which pinned min at 0. None when the image has no samples to measure.
    """
    hist = approximate_image_histogram(image)
    if hist is None or hist.NumSamples <= 0:
        return None
    tissue = copy.deepcopy(hist)
    tissue.Bins[0] = 0
    if sum(tissue.Bins) <= 0:
        tissue = hist
    lo, hi = tissue.AutoLevel(AUTO_MIN_PERCENTILE, AUTO_MAX_PERCENTILE)
    return normalize_contrast(ImageDisplayContrast(
        min=float(lo), max=float(hi), gamma=auto_gamma(hist, float(lo), float(hi)), auto_gamma=True))


def image_file_is_crushed(path: str | None) -> bool:
    """True when *path* is a noise-crushed (Quantized) PNG, which carries a ``nornir_crush`` chunk.

    Crushed images hold noise-step codes in the low part of the 8-bit range, so they look nearly black
    without a contrast stretch. Only the PNG header is read.
    """
    if not path or not path.lower().endswith(".png"):
        return False
    try:
        with Image.open(path) as im:
            return _CRUSH_PNG_CHUNK in im.info
    except OSError:
        logger.debug("Could not read PNG header of %s", path, exc_info=True)
        return False


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
    return ImageDisplayContrast(min=lo, max=hi, gamma=gamma, auto_gamma=bool(contrast.auto_gamma))


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


def contrast_key(path: str) -> str:
    """The key of an image file in ``UISettings.image_contrasts``: its absolute path, case-folded on Windows."""
    return os.path.normcase(os.path.abspath(path))


def image_path_for_space(space: Space, settings: AppSettings) -> str | None:
    """The image file shown in *space*, or None when there is none."""
    image = settings.stos.target_image if space == Space.Target else settings.stos.source_image
    return image.image_fullpath if image is not None and image.image_fullpath else None


def saved_image_contrast(path: str | None, settings: AppSettings) -> ImageDisplayContrast | None:
    """The contrast saved for the image at *path*, or None when it has none."""
    if not path:
        return None
    saved = settings.ui.image_contrasts.get(contrast_key(path))
    return normalize_contrast(saved) if saved is not None else None


@inject
def contrast_for_space(
        space: Space,
        settings: AppSettings = Provide[IContainer.settings],
) -> ImageDisplayContrast:
    """Return normalized contrast for Source or Target: the shown image's own, else the space's."""
    saved = saved_image_contrast(image_path_for_space(space, settings), settings)
    if saved is not None:
        return saved
    if space == Space.Target:
        return normalize_contrast(settings.ui.target_contrast)
    return normalize_contrast(settings.ui.source_contrast)


def set_contrast_for_space(
        space: Space,
        contrast: ImageDisplayContrast,
        settings: AppSettings,
) -> ImageDisplayContrast:
    """Write normalized contrast for *space* and for the image it shows; return stored value."""
    normalized = normalize_contrast(contrast)
    if space == Space.Target:
        settings.ui.target_contrast = normalized
    else:
        settings.ui.source_contrast = normalized
    path = image_path_for_space(space, settings)
    if path:
        contrasts = dict(settings.ui.image_contrasts)
        contrasts[contrast_key(path)] = normalized
        settings.ui.image_contrasts = contrasts
    return normalized


def contrast_for_loaded_image(
        space: Space,
        path: str | None,
        image: NDArray | None,
        settings: AppSettings,
) -> ImageDisplayContrast:
    """Give *space* the contrast of the image just loaded into it, and return it.

    The image's saved contrast when it has one. Otherwise Auto for a noise-crushed image, which
    looks nearly black without a stretch, and the identity for any other image, so a new image
    never shows the contrast of the pair opened before it (RC3 1025 showed 0325's).
    """
    saved = saved_image_contrast(path, settings)
    if saved is not None:
        contrast = saved
    elif image is not None and image_file_is_crushed(path):
        contrast = auto_contrast(image) or ImageDisplayContrast()
    else:
        contrast = ImageDisplayContrast()
    if space == Space.Target:
        settings.ui.target_contrast = contrast
    else:
        settings.ui.source_contrast = contrast
    if saved is None and path and not is_identity_contrast(contrast):
        contrasts = dict(settings.ui.image_contrasts)
        contrasts[contrast_key(path)] = contrast
        settings.ui.image_contrasts = contrasts
    return contrast


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
