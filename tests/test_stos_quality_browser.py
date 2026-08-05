"""Tests for Pyre STOS quality score attach helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip('PyQt6')

from nornir_imageregistration.stos_quality import (
    PairZnccResult,
    QualityCache,
    load_quality_cache,
    merge_entry,
    save_quality_cache,
)
from pyre.stos_manual_paths import StosBrowserRow, StosFileSource
from pyre.stos_quality_browser import (
    attach_quality_scores,
    format_quality_score,
    histogram_from_rows,
    score_path_for_row,
)


def test_format_quality_score() -> None:
    assert format_quality_score(None) == "\u2014"
    assert format_quality_score(0.7123) == "0.712"


def test_score_path_prefers_source(tmp_path: Path) -> None:
    auto = tmp_path / 'a.stos'
    manual = tmp_path / 'Manual' / 'a.stos'
    auto.write_text('x')
    manual.parent.mkdir()
    manual.write_text('y')
    row = StosBrowserRow('a.stos', str(auto), str(manual))
    assert score_path_for_row(row, StosFileSource.original) == str(auto)
    assert score_path_for_row(row, StosFileSource.manual) == str(manual)
    assert score_path_for_row(row, StosFileSource.auto) == str(manual)


def test_attach_quality_scores_and_histogram(tmp_path: Path) -> None:
    auto = tmp_path / 'a.stos'
    auto.write_text('transform')
    cache = QualityCache()
    merge_entry(
        cache,
        'a.stos',
        pair=PairZnccResult(
            pair_zncc=0.55,
            downsample=16.0,
            stos_checksum='',
            stos_mtime_ns=auto.stat().st_mtime_ns,
            max_side=2048,
        ),
    )
    save_quality_cache(str(tmp_path), cache)

    rows = [StosBrowserRow('a.stos', str(auto), None)]
    updated, _loaded, stale = attach_quality_scores(
        str(tmp_path),
        rows,
        StosFileSource.auto,
        cache=load_quality_cache(str(tmp_path)),
    )
    assert updated[0].quality_score == 0.55
    assert stale == []
    hist = histogram_from_rows(updated)
    assert hist.NumSamples == 1
