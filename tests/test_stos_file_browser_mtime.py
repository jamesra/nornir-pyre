"""Tests for STOS browser last-modified column formatting."""

from __future__ import annotations

from datetime import datetime, timedelta

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from pyre.ui.windows.stosfilebrowser import format_stos_browser_mtime


def test_format_stos_browser_mtime_none_is_em_dash() -> None:
    assert format_stos_browser_mtime(None) == "\u2014"


def test_format_stos_browser_mtime_today_is_24h_time() -> None:
    now = datetime(2026, 9, 17, 14, 35, 0)
    mtime = now.replace(hour=9, minute=7, second=0).timestamp()
    assert format_stos_browser_mtime(mtime, now=now) == "09:07"


def test_format_stos_browser_mtime_other_day_is_iso_two_digit_year() -> None:
    now = datetime(2026, 9, 17, 14, 35, 0)
    when = datetime(2026, 1, 5, 23, 59, 0)
    assert format_stos_browser_mtime(when.timestamp(), now=now) == "26-01-05"


@given(hour=st.integers(0, 23), minute=st.integers(0, 59), second=st.integers(0, 59))
@settings(max_examples=40)
def test_same_local_date_always_hhmm(hour: int, minute: int, second: int) -> None:
    now = datetime(2026, 9, 17, 12, 0, 0)
    when = now.replace(hour=hour, minute=minute, second=second)
    assume(datetime.fromtimestamp(when.timestamp()).date() == now.date())
    assert format_stos_browser_mtime(when.timestamp(), now=now) == f"{hour:02d}:{minute:02d}"


@given(days=st.integers(-400, 400))
@settings(max_examples=40)
def test_other_local_date_is_iso_yy_mm_dd(days: int) -> None:
    now = datetime(2026, 9, 17, 12, 0, 0)
    when = now + timedelta(days=days)
    local = datetime.fromtimestamp(when.timestamp())
    assume(local.date() != now.date())
    assert format_stos_browser_mtime(when.timestamp(), now=now) == local.strftime("%y-%m-%d")
