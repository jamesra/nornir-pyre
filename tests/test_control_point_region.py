"""Tests for rectangular and polygon control-point region queries."""

from __future__ import annotations

import unittest

import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st

from nornir_imageregistration.transforms.meshwithrbffallback import MeshWithRBFFallback

from pyre.commands.stos.regionselectcommand import RegionSelectShape, indices_in_region
from pyre.controllers.transformcontroller import TransformController
from pyre.interfaces.viewtype import ViewType
from pyre.space import Space
from pyre.viewmodels.controlpointmap import ControlPointMap


def _mesh() -> MeshWithRBFFallback:
    points = np.array([
        [10.0, 20.0, 100.0, 200.0],
        [30.0, 40.0, 300.0, 400.0],
        [50.0, 60.0, 500.0, 600.0],
        [70.0, 80.0, 700.0, 800.0],
    ], dtype=np.float32)
    return MeshWithRBFFallback(points)


class TestControlPointRegionQueries(unittest.TestCase):
    """find_in_rect / find_in_polygon in panel and composite display space."""

    def setUp(self) -> None:
        self.controller = TransformController(_mesh())
        self.cmap = ControlPointMap(self.controller, Space.Source)

    def test_find_in_rect_includes_interior_and_edge(self) -> None:
        hits = self.cmap.find_in_rect((100.0, 200.0), (300.0, 400.0))
        self.assertEqual(hits, {0, 1})

    def test_find_in_rect_empty_when_away_from_points(self) -> None:
        self.assertEqual(self.cmap.find_in_rect((0.0, 0.0), (1.0, 1.0)), set())

    def test_find_in_rect_rejects_non_finite_corners(self) -> None:
        self.assertEqual(self.cmap.find_in_rect((np.nan, 0.0), (10.0, 10.0)), set())

    def test_find_in_polygon_triangle_around_first_point(self) -> None:
        polygon = np.array([
            [90.0, 190.0],
            [110.0, 190.0],
            [100.0, 210.0],
        ], dtype=np.float64)
        self.assertEqual(self.cmap.find_in_polygon(polygon), {0})

    def test_find_in_polygon_includes_vertex(self) -> None:
        pts = self.cmap.points
        polygon = np.array([
            pts[0],
            pts[0] + np.array([20.0, 0.0]),
            pts[0] + np.array([0.0, 20.0]),
        ], dtype=np.float64)
        self.assertIn(0, self.cmap.find_in_polygon(polygon))

    def test_find_in_polygon_rejects_short_path(self) -> None:
        self.assertEqual(self.cmap.find_in_polygon(np.array([[0.0, 0.0], [1.0, 1.0]])), set())

    def test_composite_source_rect_uses_display_points(self) -> None:
        identity = MeshWithRBFFallback(np.array([
            [0.0, 0.0, 0.0, 0.0],
            [0.0, 10.0, 0.0, 10.0],
            [10.0, 0.0, 10.0, 0.0],
            [10.0, 10.0, 10.0, 10.0],
        ], dtype=np.float32))
        controller = TransformController(identity)
        cmap = ControlPointMap(controller, Space.Source, ViewType.Composite)
        display = cmap.points
        self.assertTrue(np.all(np.isfinite(display)))
        pad = np.array([1.0, 1.0])
        hits = cmap.find_in_rect(display[0] - pad, display[0] + pad)
        self.assertIn(0, hits)

    def test_indices_in_region_box_matches_find_in_rect(self) -> None:
        corners = np.array([[100.0, 200.0], [300.0, 400.0]])
        self.assertEqual(
            indices_in_region(self.cmap, RegionSelectShape.BOX, corners),
            self.cmap.find_in_rect(corners[0], corners[1]),
        )

    def test_indices_in_region_lasso_matches_find_in_polygon(self) -> None:
        polygon = np.array([
            [90.0, 190.0],
            [110.0, 190.0],
            [100.0, 210.0],
        ], dtype=np.float64)
        self.assertEqual(
            indices_in_region(self.cmap, RegionSelectShape.LASSO, polygon),
            self.cmap.find_in_polygon(polygon),
        )


class TestFindInRectProperties(unittest.TestCase):
    """Random boxes over a fixed mesh contain exactly the in-bounds source points."""

    @given(
        y0=st.floats(50.0, 750.0, allow_nan=False, allow_infinity=False),
        x0=st.floats(150.0, 850.0, allow_nan=False, allow_infinity=False),
        height=st.floats(1.0, 400.0, allow_nan=False, allow_infinity=False),
        width=st.floats(1.0, 400.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=40, deadline=None)
    def test_rect_matches_inclusive_bounds(
            self, y0: float, x0: float, height: float, width: float) -> None:
        cmap = ControlPointMap(TransformController(_mesh()), Space.Source)
        corner_b = (y0 + height, x0 + width)
        hits = cmap.find_in_rect((y0, x0), corner_b)
        pts = np.asarray(cmap.points, dtype=np.float64)
        ymin, ymax = min(y0, y0 + height), max(y0, y0 + height)
        xmin, xmax = min(x0, x0 + width), max(x0, x0 + width)
        expected = {
            i for i, p in enumerate(pts)
            if ymin <= p[0] <= ymax and xmin <= p[1] <= xmax
        }
        self.assertEqual(hits, expected)
