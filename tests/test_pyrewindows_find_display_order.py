"""Tests for PyreWindowBase.findDisplayOrder (left-to-right display ordering)."""

from __future__ import annotations

import unittest
from typing import Any
from unittest import mock

from hypothesis import example, given
from hypothesis import strategies as st

from pyre.ui.windows.pyrewindows import PyreWindowBase


class _Rect:
    """Minimal stand-in for QRect: only x() is used by the ordering."""

    def __init__(self, x: int, tag: int) -> None:
        self._x = x
        self.tag = tag

    def x(self) -> int:
        return self._x


class _Screen:
    def __init__(self, rect: _Rect) -> None:
        self._rect = rect

    def availableGeometry(self) -> _Rect:
        return self._rect


def _old_selection_sort(sizes: list[_Rect]) -> list[_Rect]:
    """Reference copy of the hand-rolled selection sort used before the change."""
    ordered: list[_Rect] = []
    remaining = sizes.copy()
    while len(remaining) > 0:
        smallest: tuple[int, int] | None = None
        for i in range(len(remaining)):
            if smallest is None:
                smallest = remaining[i].x(), i
            if remaining[i].x() < smallest[0]:
                smallest = remaining[i].x(), i
        assert smallest is not None
        ordered.append(remaining.pop(smallest[1]))
    return ordered


def _find_order(rects: list[_Rect]) -> list[Any]:
    screens = [_Screen(r) for r in rects]
    with mock.patch("PyQt6.QtGui.QGuiApplication.screens", return_value=screens):
        return PyreWindowBase.findDisplayOrder(mock.Mock(spec=PyreWindowBase))


class TestFindDisplayOrder(unittest.TestCase):
    """findDisplayOrder returns available geometries sorted by x, ties in screen order."""

    def test_empty(self) -> None:
        self.assertEqual(_find_order([]), [])

    def test_sorts_by_x_with_negative_origin(self) -> None:
        rects = [_Rect(1920, 0), _Rect(-1920, 1), _Rect(0, 2)]
        self.assertEqual([r.tag for r in _find_order(rects)], [1, 2, 0])

    def test_ties_keep_screen_order(self) -> None:
        rects = [_Rect(0, 0), _Rect(0, 1), _Rect(-5, 2), _Rect(0, 3)]
        self.assertEqual([r.tag for r in _find_order(rects)], [2, 0, 1, 3])

    @given(xs=st.lists(st.integers(min_value=-10000, max_value=10000), max_size=8))
    @example(xs=[0, 0, 0])
    def test_matches_old_selection_sort(self, xs: list[int]) -> None:
        rects = [_Rect(x, i) for i, x in enumerate(xs)]
        self.assertEqual([r.tag for r in _find_order(rects)],
                         [r.tag for r in _old_selection_sort(rects)])
