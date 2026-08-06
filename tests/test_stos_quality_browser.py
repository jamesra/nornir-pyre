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
    percentile_to_rgb,
    quality_score_rgb,
    score_path_for_row,
    score_to_percentile,
    scores_from_rows,
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


def test_score_to_percentile_needs_two_samples() -> None:
    assert score_to_percentile(0.5, [0.5]) is None
    assert score_to_percentile(0.5, []) is None


def test_score_to_percentile_empirical_cdf() -> None:
    scores = [0.1, 0.2, 0.3, 0.4]
    assert score_to_percentile(0.1, scores) == pytest.approx(0.25)
    assert score_to_percentile(0.4, scores) == pytest.approx(1.0)
    assert score_to_percentile(0.25, scores) == pytest.approx(0.5)


def test_percentile_to_rgb_mid_near_white() -> None:
    r, g, b = percentile_to_rgb(0.5)
    assert r == pytest.approx(0xE8 / 255.0, abs=0.05)
    assert g == pytest.approx(0xE8 / 255.0, abs=0.05)
    assert b == pytest.approx(0xE8 / 255.0, abs=0.05)


def test_percentile_to_rgb_low_magenta_high_green() -> None:
    low = percentile_to_rgb(0.0)
    high = percentile_to_rgb(1.0)
    # Magenta: R and B elevated vs G
    assert low[0] > low[1]
    assert low[2] > low[1]
    # Green: G elevated vs R and B
    assert high[1] > high[0]
    assert high[1] > high[2]


def test_quality_score_rgb_endpoints() -> None:
    scores = [0.1, 0.2, 0.3, 0.4, 0.5]
    low = quality_score_rgb(0.1, scores)
    mid = quality_score_rgb(0.3, scores)
    high = quality_score_rgb(0.5, scores)
    assert low is not None and mid is not None and high is not None
    # Low is magenta-ward (R,B > G); high is green-ward (G dominant).
    assert low[0] > low[1] and low[2] > low[1]
    assert high[1] > high[0] and high[1] > high[2]
    # Mid sits nearer soft white than the extremes.
    white = (0xE8 / 255.0, 0xE8 / 255.0, 0xE8 / 255.0)

    def dist(rgb: tuple[float, float, float]) -> float:
        return sum((a - b) ** 2 for a, b in zip(rgb, white))

    assert dist(mid) < dist(low)
    assert dist(mid) < dist(high)
    assert quality_score_rgb(0.5, [0.5]) is None


def test_scores_from_rows() -> None:
    rows = [
        StosBrowserRow('a.stos', 'a', None).with_quality_score(0.2),
        StosBrowserRow('b.stos', 'b', None).with_quality_score(None),
        StosBrowserRow('c.stos', 'c', None).with_quality_score(0.8),
    ]
    assert scores_from_rows(rows) == [0.2, 0.8]
