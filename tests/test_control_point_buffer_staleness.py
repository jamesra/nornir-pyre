"""Tests for the control-point GL buffer staleness early-out.

`PointView.points` stores XY-swapped rows but its getter returns them unswapped, so the
staleness check in `TransformControllerView._OnTransformChange` was comparing XY buffer
contents against YX controller points. That agreed only when every point had y == x, so an
unchanged transform re-uploaded the whole control-point buffer on every change event.
"""

from __future__ import annotations

import unittest

import numpy as np
from nornir_imageregistration.transforms.meshwithrbffallback import MeshWithRBFFallback

from pyre.controllers.transformcontroller import TransformController
from pyre.views.transformcontrollerview import TransformControllerView


def _mesh() -> MeshWithRBFFallback:
    points = np.array([
        [0.0, 0.0, 100.0, 100.0],
        [0.0, 100.0, 100.0, 200.0],
        [100.0, 0.0, 200.0, 100.0],
        [100.0, 100.0, 200.0, 200.0],
    ], dtype=np.float32)
    return MeshWithRBFFallback(points)


class _FakePointView:
    """Mimics PointView's storage: swap to XY on set, return stored rows on get."""

    def __init__(self) -> None:
        self._points: np.ndarray = np.zeros((0, 4), dtype=np.float32)
        self._texture: np.ndarray = np.zeros((0, 1), dtype=np.float32)
        self.upload_count = 0

    @property
    def points(self) -> np.ndarray:
        return self._points

    @points.setter
    def points(self, value: np.ndarray) -> None:
        value = np.asarray(value, dtype=np.float32)
        self._points = TransformController.swap_columns_to_XY(value)
        self.upload_count += 1
        if self._texture.shape[0] != self._points.shape[0]:
            self._texture = np.zeros((self._points.shape[0], 1), dtype=np.float32)

    @property
    def texture_index(self) -> np.ndarray:
        return self._texture


class _StubView:
    """Just the attributes `_OnTransformChange` touches."""

    def __init__(self, controller: TransformController) -> None:
        self._controlpoint_view = _FakePointView()
        self._transform_controller = controller
        self._selection_mask = None
        self.selected: object = object()

    def _control_point_buffer_is_current(self, buf_points, tc_points) -> bool:
        # Resolved at call time so this module still imports against unfixed code, where
        # _OnTransformChange carries the comparison inline and never reaches this.
        return TransformControllerView._control_point_buffer_is_current(buf_points, tc_points)

    def fire(self, controller: TransformController | None = None) -> None:
        TransformControllerView._OnTransformChange(self, controller)  # type: ignore[arg-type]


class TestThePremise(unittest.TestCase):
    """Why the old direct comparison could not work."""

    def test_the_swap_is_its_own_inverse(self) -> None:
        points = (np.random.default_rng(7).random((6, 4)) * 1000).astype(np.float32)
        twice = TransformController.swap_columns_to_XY(
            TransformController.swap_columns_to_XY(points))
        np.testing.assert_array_equal(points, twice)

    def test_the_old_comparison_disagreed_for_ordinary_points(self) -> None:
        points = (np.random.default_rng(7).random((6, 4)) * 1000).astype(np.float32)
        buffer_contents = TransformController.swap_columns_to_XY(points)
        self.assertFalse(np.allclose(buffer_contents, points),
                         'the pre-fix check compared XY against YX and so never matched')

    def test_the_old_comparison_only_agreed_on_the_diagonal(self) -> None:
        diagonal = np.array([[5.0, 5.0, 9.0, 9.0], [1.0, 1.0, 2.0, 2.0]], dtype=np.float32)
        self.assertTrue(np.allclose(
            TransformController.swap_columns_to_XY(diagonal), diagonal))


class TestTheStalenessCheck(unittest.TestCase):
    """The helper compares both sides in YX."""

    @staticmethod
    def current(buf: np.ndarray | None, tc: np.ndarray) -> bool:
        return TransformControllerView._control_point_buffer_is_current(buf, tc)

    def setUp(self) -> None:
        self.points = (np.random.default_rng(3).random((8, 4)) * 1000).astype(np.float32)
        self.buffer = TransformController.swap_columns_to_XY(self.points)

    def test_a_buffer_holding_the_same_points_is_current(self) -> None:
        self.assertTrue(self.current(self.buffer, self.points))

    def test_a_moved_point_is_not_current(self) -> None:
        moved = self.points.copy()
        moved[3, 0] += 5.0
        self.assertFalse(self.current(self.buffer, moved))

    def test_a_swapped_pair_is_not_current(self) -> None:
        """y and x differ, so mixing the columns must still register as stale."""
        swapped = self.points.copy()
        swapped[:, [0, 1]] = swapped[:, [1, 0]]
        self.assertFalse(self.current(self.buffer, swapped))

    def test_a_length_change_is_not_current(self) -> None:
        self.assertFalse(self.current(self.buffer, self.points[:4]))
        self.assertFalse(self.current(self.buffer[:4], self.points))

    def test_an_empty_buffer_is_not_current(self) -> None:
        self.assertFalse(self.current(np.zeros((0, 4), dtype=np.float32), self.points))

    def test_a_missing_or_malformed_buffer_is_not_current(self) -> None:
        for buf in (None,
                    np.zeros((0,), dtype=np.float32),
                    np.zeros((8, 2), dtype=np.float32)):
            with self.subTest(buf=None if buf is None else buf.shape):
                self.assertFalse(self.current(buf, self.points))

    def test_two_empty_sides_agree(self) -> None:
        empty = np.zeros((0, 4), dtype=np.float32)
        self.assertTrue(self.current(empty, empty))


class TestTheUploadIsSkipped(unittest.TestCase):
    """End-to-end: an unchanged transform must not re-upload."""

    def setUp(self) -> None:
        self.controller = TransformController(_mesh())
        self.view = _StubView(self.controller)

    def test_the_first_change_uploads(self) -> None:
        self.view.fire(self.controller)
        self.assertEqual(1, self.view._controlpoint_view.upload_count)

    def test_a_repeat_change_does_not_upload(self) -> None:
        self.view.fire(self.controller)
        baseline = self.view._controlpoint_view.upload_count
        for _ in range(5):
            self.view.fire(self.controller)
        self.assertEqual(baseline, self.view._controlpoint_view.upload_count,
                         'the early-out should absorb repeat events for an unchanged transform')

    def test_the_buffer_still_matches_the_controller_after_the_early_out(self) -> None:
        self.view.fire(self.controller)
        self.view.fire(self.controller)
        stored = TransformController.swap_columns_to_XY(self.view._controlpoint_view.points)
        np.testing.assert_allclose(self.controller.points, stored, atol=1e-4)

    def test_a_real_change_still_uploads(self) -> None:
        self.view.fire(self.controller)
        baseline = self.view._controlpoint_view.upload_count
        self.controller.SetPoint(0, 12.0, 34.0)
        self.view.fire(self.controller)
        self.assertEqual(baseline + 1, self.view._controlpoint_view.upload_count)
        stored = TransformController.swap_columns_to_XY(self.view._controlpoint_view.points)
        np.testing.assert_allclose(self.controller.points, stored, atol=1e-4)

    def test_an_added_point_still_uploads(self) -> None:
        self.view.fire(self.controller)
        baseline = self.view._controlpoint_view.upload_count
        self.controller.TryAddPoint(50.0, 50.0)
        self.view.fire(self.controller)
        self.assertEqual(baseline + 1, self.view._controlpoint_view.upload_count)
        self.assertEqual(self.controller.points.shape[0],
                         self.view._controlpoint_view.points.shape[0])

    def test_an_interactive_edit_is_still_ignored(self) -> None:
        self.controller._interactive_edit_depth = 1
        self.assertTrue(self.controller.interactive_edit_in_progress)
        self.view.fire(self.controller)
        self.assertEqual(0, self.view._controlpoint_view.upload_count)


if __name__ == '__main__':
    unittest.main()
