"""Tests for composite phase-correlation cell overlays on busy control points."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import numpy as np
from hypothesis import example, given, settings
from hypothesis import strategies as st
from numpy.typing import NDArray
from PyQt6.QtCore import QThread

from nornir_imageregistration.alignment_record import AlignmentRecord
from nornir_imageregistration.transforms.meshwithrbffallback import MeshWithRBFFallback
from pyre.controllers.transformcontroller import TransformController
from pyre.interfaces.viewtype import ViewType
from pyre.views.registration_roi_overlay import (
    REGISTRATION_ROI_FADE_SECONDS,
    RegistrationRoiFadeTracker,
    RegistrationRoiOverlay,
    alignment_area_yx,
    combined_mvp_for_roi,
    model_matrix_for_roi_overlay,
    phase_correlation_roi_bounds_yx,
    phase_correlation_roi_overlays,
    registration_roi_fade_alpha,
    should_draw_registration_roi,
)


def _fake_qapp() -> MagicMock:
    app = MagicMock()
    app.thread.return_value = QThread.currentThread()
    return app


def _mesh(n_points: int = 4) -> MeshWithRBFFallback:
    points = np.array(
        [
            [float(i * 10), float(i * 20), float(i * 100), float(i * 200)]
            for i in range(n_points)
        ],
        dtype=np.float64,
    )
    return MeshWithRBFFallback(points)


def _record() -> AlignmentRecord:
    return AlignmentRecord(peak=(0.0, 0.0), weight=1.0, angle=0.0)


def _gl_transform(numpy_mvp: NDArray[np.floating], xy: tuple[float, float]) -> NDArray[np.floating]:
    """Apply a translation-last-row numpy matrix the way ColorShader uploads it to GLSL."""
    gl_m = np.asarray(numpy_mvp, dtype=np.float64).T
    out = gl_m @ np.array((xy[0], xy[1], 0.0, 1.0), dtype=np.float64)
    return out[:2]


class TestRegistrationRoiFade(unittest.TestCase):
    @example(0.0)
    @example(2.5)
    @example(5.0)
    @example(6.0)
    @given(st.floats(min_value=-1.0, max_value=10.0, allow_nan=False, allow_infinity=False))
    @settings(max_examples=40)
    def test_linear_fade(self, elapsed: float) -> None:
        alpha = registration_roi_fade_alpha(elapsed, REGISTRATION_ROI_FADE_SECONDS)
        if elapsed <= 0.0:
            self.assertEqual(alpha, 1.0)
        elif elapsed >= REGISTRATION_ROI_FADE_SECONDS:
            self.assertEqual(alpha, 0.0)
        else:
            self.assertAlmostEqual(alpha, 1.0 - elapsed / REGISTRATION_ROI_FADE_SECONDS)


class TestRegistrationRoiGeometry(unittest.TestCase):
    def test_alignment_area_square_and_fallback(self) -> None:
        self.assertEqual(alignment_area_yx(np.array([128, 256])), (128.0, 256.0))
        self.assertEqual(alignment_area_yx(None, fallback=(64, 64)), (64.0, 64.0))
        self.assertEqual(alignment_area_yx(np.array([32])), (32.0, 32.0))

    @given(
        cy=st.floats(min_value=-1e3, max_value=1e3, allow_nan=False, allow_infinity=False),
        cx=st.floats(min_value=-1e3, max_value=1e3, allow_nan=False, allow_infinity=False),
        height=st.floats(min_value=1.0, max_value=512.0, allow_nan=False, allow_infinity=False),
        width=st.floats(min_value=1.0, max_value=512.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=40)
    def test_bounds_centered_on_control_point(
            self, cy: float, cx: float, height: float, width: float) -> None:
        bounds = phase_correlation_roi_bounds_yx((cy, cx), (height, width))
        mid_y = (bounds[0] + bounds[2]) / 2.0
        mid_x = (bounds[1] + bounds[3]) / 2.0
        self.assertAlmostEqual(mid_y, cy)
        self.assertAlmostEqual(mid_x, cx)
        self.assertAlmostEqual(bounds[2] - bounds[0], height)
        self.assertAlmostEqual(bounds[3] - bounds[1], width)

    def test_unit_quad_maps_to_roi_corners(self) -> None:
        overlay = RegistrationRoiOverlay(center_yx=(10.0, 20.0), size_yx=(8.0, 6.0), alpha=1.0)
        model = model_matrix_for_roi_overlay(overlay)
        bounds = phase_correlation_roi_bounds_yx(overlay.center_yx, overlay.size_yx)
        np.testing.assert_allclose(_gl_transform(model, (-0.5, -0.5)), (bounds[1], bounds[0]))
        np.testing.assert_allclose(_gl_transform(model, (0.5, 0.5)), (bounds[3], bounds[2]))

    def test_combined_mvp_applies_model_then_view(self) -> None:
        overlay = RegistrationRoiOverlay(center_yx=(4.0, 6.0), size_yx=(2.0, 2.0), alpha=1.0)
        identity = np.eye(4, dtype=np.float64)
        mvp = combined_mvp_for_roi(identity, overlay)
        np.testing.assert_allclose(
            _gl_transform(mvp, (0.0, 0.0)),
            (overlay.center_yx[1], overlay.center_yx[0]),
        )


class TestRegistrationRoiFadeTracker(unittest.TestCase):
    def test_new_ids_start_now_and_are_not_reset(self) -> None:
        tracker = RegistrationRoiFadeTracker()
        tracker.sync(frozenset({3, 7}), 10.0)
        tracker.sync(frozenset({3, 7, 9}), 11.0)
        self.assertEqual(tracker.started_at[3], 10.0)
        self.assertEqual(tracker.started_at[7], 10.0)
        self.assertEqual(tracker.started_at[9], 11.0)
        tracker.sync(frozenset({9}), 12.0)
        self.assertEqual(set(tracker.started_at), {9})
        self.assertEqual(tracker.started_at[9], 11.0)


class TestPhaseCorrelationRoiOverlays(unittest.TestCase):
    def test_composite_only(self) -> None:
        self.assertTrue(should_draw_registration_roi(ViewType.Composite))
        self.assertFalse(should_draw_registration_roi(ViewType.Source))
        self.assertFalse(should_draw_registration_roi(ViewType.Target))

    def test_overlays_use_target_points_and_alignment_area(self) -> None:
        controller = TransformController(_mesh(4))
        point_id = controller.point_id_for_index(1)
        assert point_id is not None
        area = np.array([64, 128], dtype=np.int32)
        tracker = RegistrationRoiFadeTracker()
        tracker.sync(frozenset({point_id}), 0.0)
        overlays = phase_correlation_roi_overlays(
            busy_ids=frozenset({point_id}),
            started_at=tracker.started_at,
            index_for_id=controller.index_for_point_id,
            target_points_yx=controller.TargetPoints,
            alignment_area_yx_shape=area,
            now=0.0,
        )
        self.assertEqual(len(overlays), 1)
        expected = controller.TargetPoints[1]
        self.assertAlmostEqual(overlays[0].center_yx[0], float(expected[0]))
        self.assertAlmostEqual(overlays[0].center_yx[1], float(expected[1]))
        self.assertEqual(overlays[0].size_yx, (64.0, 128.0))
        self.assertEqual(overlays[0].alpha, 1.0)

    def test_fade_and_drop_when_not_busy(self) -> None:
        controller = TransformController(_mesh(4))
        point_id = controller.point_id_for_index(0)
        assert point_id is not None
        tracker = RegistrationRoiFadeTracker()
        tracker.sync(frozenset({point_id}), 0.0)
        mid = phase_correlation_roi_overlays(
            busy_ids=frozenset({point_id}),
            started_at=tracker.started_at,
            index_for_id=controller.index_for_point_id,
            target_points_yx=controller.TargetPoints,
            alignment_area_yx_shape=(128, 128),
            now=2.5,
        )
        self.assertAlmostEqual(mid[0].alpha, 0.5)
        gone = phase_correlation_roi_overlays(
            busy_ids=frozenset({point_id}),
            started_at=tracker.started_at,
            index_for_id=controller.index_for_point_id,
            target_points_yx=controller.TargetPoints,
            alignment_area_yx_shape=(128, 128),
            now=5.0,
        )
        self.assertEqual(gone, [])
        tracker.sync(frozenset(), 5.1)
        empty = phase_correlation_roi_overlays(
            busy_ids=frozenset(),
            started_at=tracker.started_at,
            index_for_id=controller.index_for_point_id,
            target_points_yx=controller.TargetPoints,
            alignment_area_yx_shape=(128, 128),
            now=5.1,
        )
        self.assertEqual(empty, [])

    def test_enqueue_stores_alignment_area_for_overlay(self) -> None:
        controller = TransformController(_mesh(3))
        area = np.array([48, 96], dtype=np.int32)
        pool = MagicMock()
        pool.add_task = MagicMock()
        with patch("pyre.controllers.transformcontroller.QApplication") as qapp:
            qapp.instance.return_value = _fake_qapp()
            with patch(
                    "pyre.controllers.transformcontroller.pools.GetGlobalThreadPool",
                    return_value=pool,
            ):
                controller.enqueue_point_registrations(
                    [2], alignment_area=area, align_fn=lambda **_: _record())
        np.testing.assert_array_equal(controller.registration_alignment_area, area)
        point_id = controller.point_id_for_index(2)
        assert point_id is not None
        tracker = RegistrationRoiFadeTracker()
        tracker.sync(controller.busy_point_ids, 1.0)
        overlays = phase_correlation_roi_overlays(
            busy_ids=controller.busy_point_ids,
            started_at=tracker.started_at,
            index_for_id=controller.index_for_point_id,
            target_points_yx=controller.TargetPoints,
            alignment_area_yx_shape=controller.registration_alignment_area,
            now=1.0,
        )
        self.assertEqual(len(overlays), 1)
        self.assertEqual(overlays[0].size_yx, (48.0, 96.0))
        expected = controller.TargetPoints[2]
        self.assertAlmostEqual(overlays[0].center_yx[0], float(expected[0]))
        self.assertAlmostEqual(overlays[0].center_yx[1], float(expected[1]))
