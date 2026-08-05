"""Helpers for attaching STOS quality scores in the Pyre browser."""

from __future__ import annotations

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
