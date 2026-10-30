"""Tests for the single-pass host conversion behind composite control-point draw rows.

``composite_control_point_draw_rows`` mutates its result, and ``TransformController.points``
is a live view into transform storage, so the result must never alias it. The conversion is
also on the composite draw path, so it should cost one pass rather than two.
"""

from __future__ import annotations

import unittest

import numpy as np
from nornir_imageregistration.transforms.meshwithrbffallback import MeshWithRBFFallback

from pyre.controllers.transformcontroller import TransformController
from pyre.space import Space
from pyre.views.composite_display import (
    _as_numpy_f64,
    composite_control_point_draw_rows,
)


def _mesh() -> MeshWithRBFFallback:
    points = np.array([
        [0.0, 0.0, 100.0, 100.0],
        [0.0, 100.0, 100.0, 200.0],
        [100.0, 0.0, 200.0, 100.0],
        [100.0, 100.0, 200.0, 200.0],
    ], dtype=np.float32)
    return MeshWithRBFFallback(points)


class TestTheConversionHelper(unittest.TestCase):
    """_as_numpy_f64 returns a view unless a copy is requested."""

    def test_a_float64_input_is_returned_as_a_view(self) -> None:
        """This is why the draw-row caller must ask for a copy explicitly."""
        source = np.arange(8, dtype=np.float64).reshape(4, 2)
        result = _as_numpy_f64(source)
        self.assertTrue(np.shares_memory(result, source),
                        'no conversion is needed, so the helper should not copy')

    def test_requesting_a_copy_never_aliases(self) -> None:
        for dtype in (np.float32, np.float64):
            with self.subTest(dtype=np.dtype(dtype).name):
                source = np.arange(8, dtype=dtype).reshape(4, 2)
                result = _as_numpy_f64(source, copy=True)
                self.assertFalse(np.shares_memory(result, source))
                self.assertEqual(np.float64, result.dtype)
                np.testing.assert_array_equal(source.astype(np.float64), result)

    def test_a_copy_leaves_the_source_untouched(self) -> None:
        source = np.arange(8, dtype=np.float32).reshape(4, 2)
        before = source.copy()
        result = _as_numpy_f64(source, copy=True)
        result[:] = -1.0
        np.testing.assert_array_equal(before, source)

    def test_the_default_still_converts_dtype(self) -> None:
        source = np.arange(8, dtype=np.float32).reshape(4, 2)
        self.assertEqual(np.float64, _as_numpy_f64(source).dtype)


class TestTheDrawRows(unittest.TestCase):
    """The rows are unchanged and independent of live transform storage."""

    def setUp(self) -> None:
        self.controller = TransformController(_mesh())

    def test_the_rows_match_the_previous_expression(self) -> None:
        """Bit-identical to the two-pass `_as_numpy_f64(points).copy()` it replaced."""
        expected = np.asarray(self.controller.points, dtype=np.float64).copy()
        expected[:, 2:4] = expected[:, 0:2]

        rows = composite_control_point_draw_rows(self.controller, Space.Source)
        assert rows is not None
        self.assertEqual(np.float64, rows.dtype)
        np.testing.assert_array_equal(expected, rows)

    def test_the_rows_do_not_alias_the_model(self) -> None:
        points = self.controller.points
        rows = composite_control_point_draw_rows(self.controller, Space.Source)
        assert rows is not None
        self.assertFalse(np.shares_memory(rows, points),
                         'draw rows are mutated in place and must not reach into the model')

    def test_mutating_the_rows_does_not_disturb_the_transform(self) -> None:
        before = np.asarray(self.controller.points, dtype=np.float64).copy()
        rows = composite_control_point_draw_rows(self.controller, Space.Source)
        assert rows is not None
        rows[:] = -1234.0
        np.testing.assert_array_equal(
            before, np.asarray(self.controller.points, dtype=np.float64))

    def test_the_fixed_columns_carry_the_target_points(self) -> None:
        """Interpolators pass through control points, so display position is TargetPoints."""
        rows = composite_control_point_draw_rows(self.controller, Space.Source)
        assert rows is not None
        np.testing.assert_array_equal(rows[:, 0:2], rows[:, 2:4])
        np.testing.assert_allclose(rows[:, 0:2], self.controller.TargetPoints)


if __name__ == '__main__':
    unittest.main()
