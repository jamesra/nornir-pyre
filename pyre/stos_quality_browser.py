"""Helpers for attaching STOS quality scores in the Pyre browser."""

from __future__ import annotations

import math
import os
from typing import Sequence

from nornir_imageregistration.stos_quality import (
    QualityCache,
    build_quality_histogram,
    cache_key_for_stos,
    entry_is_stale,
    load_quality_cache,
)
from nornir_shared.histogram import Histogram

from pyre.stos_manual_paths import StosBrowserRow, StosFileSource

# Diverging ZNCC text colors (sRGB 0–1): low magenta → mid soft white → high green.
_COLOR_LOW: tuple[float, float, float] = (0xE0 / 255.0, 0x40 / 255.0, 0xA0 / 255.0)
_COLOR_MID: tuple[float, float, float] = (0xE8 / 255.0, 0xE8 / 255.0, 0xE8 / 255.0)
_COLOR_HIGH: tuple[float, float, float] = (0x3D / 255.0, 0xCC / 255.0, 0x6E / 255.0)
_PERCENTILE_SOFTEN_K: float = 1.75


def score_path_for_row(row: StosBrowserRow, source: StosFileSource) -> str | None:
    """Return the ``.stos`` path whose quality score should be shown for *row*."""
    preferred = row.load_path_for_source(source)
    if preferred is not None and os.path.isfile(preferred):
        return preferred
    return row.default_load_path


def attach_quality_scores(
        group_folder: str,
        rows: Sequence[StosBrowserRow],
        source: StosFileSource,
        *,
        cache: QualityCache | None = None,
) -> tuple[list[StosBrowserRow], QualityCache, list[str]]:
    """Attach non-stale scores to *rows*; return updated rows, cache, and stale paths."""
    if cache is None:
        cache = load_quality_cache(group_folder)
    updated: list[StosBrowserRow] = []
    stale_paths: list[str] = []
    for row in rows:
        path = score_path_for_row(row, source)
        score: float | None = None
        if path is not None and os.path.isfile(path):
            key = cache_key_for_stos(group_folder, path)
            entry = cache.entries.get(key)
            if entry_is_stale(entry, path):
                stale_paths.append(path)
            elif entry is not None and entry.get('pair_zncc') is not None:
                try:
                    score = float(entry['pair_zncc'])
                except (TypeError, ValueError):
                    score = None
                    stale_paths.append(path)
        updated.append(row.with_quality_score(score))
    return updated, cache, stale_paths


def histogram_from_rows(rows: Sequence[StosBrowserRow]) -> Histogram:
    """Build an in-memory quality histogram from rows that already have scores."""
    scores = [float(row.quality_score) for row in rows if row.quality_score is not None]
    return build_quality_histogram(scores)


def format_quality_score(score: float | None) -> str:
    """Format a ZNCC score for the browser table column."""
    if score is None:
        return "\u2014"
    return f"{score:.3f}"


def scores_from_rows(rows: Sequence[StosBrowserRow]) -> list[float]:
    """Return non-None quality scores from *rows*."""
    return [float(row.quality_score) for row in rows if row.quality_score is not None]


def score_to_percentile(score: float, all_scores: Sequence[float]) -> float | None:
    """Empirical CDF of *score* in *all_scores*: fraction of values ``<= score``.

    Returns ``None`` when there are fewer than two scores (no useful distribution).
    """
    n = len(all_scores)
    if n < 2:
        return None
    return sum(1 for value in all_scores if value <= score) / float(n)


def _lerp_rgb(
        a: tuple[float, float, float],
        b: tuple[float, float, float],
        t: float,
) -> tuple[float, float, float]:
    t = max(0.0, min(1.0, t))
    return (
        a[0] + (b[0] - a[0]) * t,
        a[1] + (b[1] - a[1]) * t,
        a[2] + (b[2] - a[2]) * t,
    )


def percentile_to_rgb(
        percentile: float,
        *,
        soften_k: float = _PERCENTILE_SOFTEN_K,
) -> tuple[float, float, float]:
    """Map percentile in ``[0, 1]`` to diverging sRGB (magenta → white → green).

    A centered ``tanh`` softens the mid-band so typical ranks stay near white.
    """
    p = max(0.0, min(1.0, float(percentile)))
    t = 0.5 + 0.5 * math.tanh(soften_k * (2.0 * p - 1.0))
    if t < 0.5:
        return _lerp_rgb(_COLOR_LOW, _COLOR_MID, t / 0.5)
    return _lerp_rgb(_COLOR_MID, _COLOR_HIGH, (t - 0.5) / 0.5)


def quality_score_rgb(
        score: float,
        all_scores: Sequence[float],
) -> tuple[float, float, float] | None:
    """Return sRGB 0–1 for *score* vs *all_scores*, or ``None`` if not colorable."""
    percentile = score_to_percentile(score, all_scores)
    if percentile is None:
        return None
    return percentile_to_rgb(percentile)
