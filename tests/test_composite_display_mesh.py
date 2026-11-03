"""Tests for composite display-space helpers (rigid and mesh/grid)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import numpy as np
from nornir_imageregistration.transforms.meshwithrbffallback import MeshWithRBFFallback
from nornir_imageregistration.transforms import Rigid

from pyre.controllers.transformcontroller import TransformController
from pyre.viewmodels.controlpointmap import ControlPointMap
from pyre.interfaces.viewtype import ViewType
from pyre.space import Space
from pyre.views.composite_display import (
    camera_lookat_from_target_space,
    composite_control_point_draw_rows,
    composite_tile_cull_rect,
    display_lookat_for_composite,
    target_space_lookat_for_stos_view,
    world_point_pair_for_composite_mouse,
    apply_composite_display_pan_delta,
)


def _mesh() -> MeshWithRBFFallback:
    points = np.array([
        [0.0, 0.0, 100.0, 100.0],
        [0.0, 100.0, 100.0, 200.0],
        [100.0, 0.0, 200.0, 100.0],
        [100.0, 100.0, 200.0, 200.0],
    ], dtype=np.float32)
    return MeshWithRBFFallback(points)


class _TestCamera:
    """Minimal camera stub with mutable lookat and translate for pan tests."""

    def __init__(self, lookat: np.ndarray) -> None:
        self._lookat = np.asarray(lookat, dtype=np.float64)

    @property
    def lookat(self) -> np.ndarray:
        return self._lookat

    @lookat.setter
    def lookat(self, point: np.ndarray) -> None:
        self._lookat = np.asarray(point, dtype=np.float64)

    def translate(self, delta: np.ndarray) -> None:
        self._lookat = self._lookat + np.asarray(delta, dtype=np.float64)


class TestCompositeDisplayMesh(unittest.TestCase):
    """Mesh/grid composite maps camera and mouse through forward/inverse transform."""

    def setUp(self) -> None:
        self.controller = TransformController(_mesh())
        # Tests exercise the mapped lookat, not the prewarm-freeze fallback.
        self.controller._rbf_prewarm_ready = True
        self.camera = MagicMock()
        self.camera.lookat = np.array([20.0, 30.0], dtype=np.float64)

    def test_display_lookat_is_camera_lookat(self) -> None:
        """Composite lookat is already target display space."""
        actual = display_lookat_for_composite(self.camera, self.controller)
        np.testing.assert_allclose(actual, self.camera.lookat, rtol=1e-5, atol=1e-5)

    def test_world_point_pair_round_trips_mesh(self) -> None:
        display = np.array([150.0, 250.0], dtype=np.float64)
        self.camera.image_coords_for_lookat.return_value = display
        pair = world_point_pair_for_composite_mouse(self.camera, self.controller, 100.0, 150.0)
        self.assertIsNotNone(pair)
        assert pair is not None
        self.assertTrue(np.all(np.isfinite(pair.source)))
        roundtrip = np.squeeze(
            self.controller.Transform(pair.source.reshape(1, 2), extrapolate=True))
        np.testing.assert_allclose(roundtrip, pair.target, rtol=1e-4, atol=1e-3)

    def test_busy_points_display_lookat_without_transform(self) -> None:
        """Queued alignments own the CUDA device; display lookat must not Transform()."""
        before = display_lookat_for_composite(self.camera, self.controller)
        point_id = self.controller.point_id_for_index(0)
        assert point_id is not None
        self.controller.mark_busy_points("register", [point_id])
        self.assertTrue(self.controller.freeze_composite_display_during_point_drag())
        with patch.object(
                self.controller, "Transform",
                side_effect=AssertionError("Transform must not run while points are busy")):
            frozen = display_lookat_for_composite(self.camera, self.controller)
        np.testing.assert_allclose(frozen, before)
        np.testing.assert_allclose(frozen, self.camera.lookat)

    def test_pan_while_busy_shifts_cached_display_lookat_without_transform(self) -> None:
        """Right-drag pan must move the frozen composite view, not chatter lookat."""
        camera = _TestCamera(np.array([20.0, 30.0], dtype=np.float64))
        display_before = display_lookat_for_composite(camera, self.controller)
        point_id = self.controller.point_id_for_index(0)
        assert point_id is not None
        self.controller.mark_busy_points("register", [point_id])
        delta_display = np.array([3.0, -5.0], dtype=np.float64)
        with (
            patch.object(
                self.controller, "Transform",
                side_effect=AssertionError("Transform must not run while points are busy")),
            patch.object(
                self.controller, "InverseTransform",
                side_effect=AssertionError("InverseTransform must not run while points are busy")),
        ):
            apply_composite_display_pan_delta(camera, self.controller, delta_display)
            display_after = display_lookat_for_composite(camera, self.controller)
        np.testing.assert_allclose(display_after, display_before + delta_display, rtol=1e-4, atol=1e-3)

    def test_cursor_lock_while_busy_shifts_cache_without_inverse(self) -> None:
        """Wheel zoom cursor-lock uses the same freeze-safe pan as right-drag."""
        camera = _TestCamera(np.array([20.0, 30.0], dtype=np.float64))
        display_before = display_lookat_for_composite(camera, self.controller)
        point_id = self.controller.point_id_for_index(0)
        assert point_id is not None
        self.controller.mark_busy_points("register", [point_id])
        cursor_shift = np.array([2.0, 4.0], dtype=np.float64)
        with (
            patch.object(
                self.controller, "Transform",
                side_effect=AssertionError("Transform must not run while points are busy")),
            patch.object(
                self.controller, "InverseTransform",
                side_effect=AssertionError("InverseTransform must not run while points are busy")),
        ):
            apply_composite_display_pan_delta(camera, self.controller, -cursor_shift)
            display_after = display_lookat_for_composite(camera, self.controller)
        np.testing.assert_allclose(display_after, display_before - cursor_shift, rtol=1e-4, atol=1e-3)

    def test_visible_rectangle_around_lookat_uses_scale_and_client_size(self) -> None:
        from pyre.views.composite_display import visible_rectangle_around_lookat

        rect = visible_rectangle_around_lookat(
            np.array([10.0, 20.0], dtype=np.float64), scale=2.0, height=100, width=200)
        np.testing.assert_allclose(rect.Center, [10.0, 20.0], rtol=1e-6, atol=1e-6)
        self.assertAlmostEqual(rect.Height, 50.0)
        self.assertAlmostEqual(rect.Width, 100.0)

    def test_composite_controlpointmap_uses_display_source_positions(self) -> None:
        cmap = ControlPointMap(self.controller, Space.Source, view_type=ViewType.Composite)
        expected = np.asarray(self.controller.Transform(self.controller.SourcePoints), dtype=np.float64)
        np.testing.assert_allclose(cmap.points, expected, atol=1e-10)
        wrong = np.asarray(self.controller.Transform(self.controller.TargetPoints), dtype=np.float64)
        self.assertFalse(np.allclose(cmap.points, wrong, atol=1e-3))

    def test_composite_control_point_draw_rows_transforms_source_columns(self) -> None:
        rows = composite_control_point_draw_rows(self.controller, Space.Source)
        self.assertIsNotNone(rows)
        assert rows is not None
        expected = np.asarray(self.controller.Transform(self.controller.SourcePoints), dtype=np.float64)
        np.testing.assert_allclose(rows[:, 2:4], expected, atol=1e-10)

    def test_rigid_world_point_pair_available(self) -> None:
        rigid = TransformController(
            Rigid(target_offset=(5.0, 10.0), source_rotation_center=(0.0, 0.0), angle=0.0))
        camera = MagicMock()
        camera.lookat = np.array([0.0, 0.0], dtype=np.float64)
        camera.image_coords_for_lookat.return_value = np.array([1.0, 2.0], dtype=np.float64)
        pair = world_point_pair_for_composite_mouse(camera, rigid, 50.0, 60.0)
        self.assertIsNotNone(pair)

    def test_composite_pan_shifts_display_lookat_by_drag_delta_mesh(self) -> None:
        camera = _TestCamera(np.array([20.0, 30.0], dtype=np.float64))
        display_before = display_lookat_for_composite(camera, self.controller)
        delta_display = np.array([0.0, -4.0], dtype=np.float64)
        apply_composite_display_pan_delta(camera, self.controller, delta_display)
        display_after = display_lookat_for_composite(camera, self.controller)
        np.testing.assert_allclose(display_after, display_before + delta_display, rtol=1e-4, atol=1e-3)

    def test_composite_pan_shifts_display_lookat_by_drag_delta_rigid(self) -> None:
        rigid = TransformController(
            Rigid(target_offset=(5.0, 10.0), source_rotation_center=(0.0, 0.0), angle=0.2))
        camera = _TestCamera(np.array([50.0, 60.0], dtype=np.float64))
        display_before = display_lookat_for_composite(camera, rigid)
        delta_display = np.array([2.0, -3.0], dtype=np.float64)
        apply_composite_display_pan_delta(camera, rigid, delta_display)
        display_after = display_lookat_for_composite(camera, rigid)
        np.testing.assert_allclose(display_after, display_before + delta_display, rtol=1e-4, atol=1e-3)

    def test_composite_tile_cull_rect_maps_display_bounds_to_source_space(self) -> None:
        import nornir_imageregistration
        from pyre.views.composite_display import (
            inverse_transform_visible_rectangle_mesh,
            transform_visible_rectangle_mesh,
        )

        source_rect = nornir_imageregistration.Rectangle.CreateFromBounds(
            np.array([10.0, 20.0, 110.0, 120.0], dtype=np.float64))
        display_rect = transform_visible_rectangle_mesh(source_rect, self.controller)
        source_cull = composite_tile_cull_rect(
            display_rect, self.controller, Space.Source, ViewType.Composite)
        target_cull = composite_tile_cull_rect(
            display_rect, self.controller, Space.Target, ViewType.Composite)
        self.assertIsNotNone(source_cull)
        assert source_cull is not None
        roundtrip = transform_visible_rectangle_mesh(source_cull, self.controller)
        np.testing.assert_allclose(
            roundtrip.BottomLeft, display_rect.BottomLeft, rtol=1e-4, atol=1e-2)
        np.testing.assert_allclose(
            [roundtrip.Height, roundtrip.Width],
            [display_rect.Height, display_rect.Width],
            rtol=1e-4,
            atol=1e-2,
        )
        np.testing.assert_allclose(
            inverse_transform_visible_rectangle_mesh(display_rect, self.controller).BottomLeft,
            source_cull.BottomLeft,
            rtol=1e-4,
            atol=1e-2,
        )
        np.testing.assert_allclose(
            target_cull.BottomLeft, display_rect.BottomLeft, rtol=1e-5, atol=1e-5)


class TestCompositeRigidGestureCameraRebase(unittest.TestCase):
    """Display-native lookat stays put through a composite rigid translate."""

    def test_display_lookat_stable_after_ending_translate_gesture(self) -> None:
        from nornir_imageregistration.transforms import CenteredSimilarity2DTransform

        model = CenteredSimilarity2DTransform(
            target_offset=(0.0, 0.0),
            source_rotation_center=(0.0, 0.0),
            angle=0.0,
            scalar=1.0,
        )
        controller = TransformController(model)
        camera = _TestCamera(np.array([40.0, 50.0], dtype=np.float64))

        controller.begin_interactive_edit(Space.Source, view_type=ViewType.Composite)
        display_before = display_lookat_for_composite(camera, controller)
        controller.Translate(np.array([12.0, -8.0], dtype=np.float64), space=Space.Source)

        display_frozen = display_lookat_for_composite(camera, controller)
        np.testing.assert_allclose(display_frozen, display_before, atol=1e-5)
        controller.end_interactive_edit()

        display_after = display_lookat_for_composite(camera, controller)
        np.testing.assert_allclose(display_after, display_before, atol=1e-4)
        np.testing.assert_allclose(camera.lookat, display_before, atol=1e-4)


class TestCompositeRegistrationCameraRebase(unittest.TestCase):
    """Remesh/clear no longer InverseTransform-rebases display-native lookat."""

    def test_clear_cache_does_not_stash_lookat_preserve(self) -> None:
        controller = TransformController(_mesh())
        controller._rbf_prewarm_ready = True
        camera = _TestCamera(np.array([20.0, 30.0], dtype=np.float64))
        before = display_lookat_for_composite(camera, controller).copy()

        controller._clear_composite_display_cache()
        pending = controller.consume_pending_composite_display_preserve()
        self.assertIsNone(pending)
        np.testing.assert_allclose(
            display_lookat_for_composite(camera, controller), before, atol=1e-5)


class TestMatchViewLookatSync(unittest.TestCase):
    """M-key helpers convert between panel camera space and Target sync space."""

    def setUp(self) -> None:
        # Rigid offset keeps forward/inverse exact without waiting on RBF prewarm.
        self.controller = TransformController(
            Rigid(target_offset=(5.0, 10.0), source_rotation_center=(0.0, 0.0), angle=0.0))
        self.source_lookat = np.array([20.0, 30.0], dtype=np.float64)
        self.target_lookat = np.squeeze(
            self.controller.Transform(self.source_lookat.reshape(1, 2)))

    def test_source_view_exports_target_space_lookat(self) -> None:
        camera = _TestCamera(self.source_lookat)
        actual = target_space_lookat_for_stos_view(
            camera, self.controller, Space.Source, ViewType.Source)
        np.testing.assert_allclose(actual, self.target_lookat, rtol=1e-5, atol=1e-5)

    def test_target_view_exports_camera_lookat(self) -> None:
        camera = _TestCamera(self.target_lookat)
        actual = target_space_lookat_for_stos_view(
            camera, self.controller, Space.Target, ViewType.Target)
        np.testing.assert_allclose(actual, self.target_lookat, rtol=1e-5, atol=1e-5)

    def test_composite_view_exports_display_lookat(self) -> None:
        # Composite lookat is target/display space (same coords as Target panel).
        camera = _TestCamera(self.target_lookat)
        actual = target_space_lookat_for_stos_view(
            camera, self.controller, Space.Source, ViewType.Composite)
        expected = display_lookat_for_composite(camera, self.controller)
        np.testing.assert_allclose(actual, expected, rtol=1e-5, atol=1e-5)
        np.testing.assert_allclose(actual, self.target_lookat, rtol=1e-5, atol=1e-5)

    def test_camera_lookat_from_target_round_trips_source(self) -> None:
        source = camera_lookat_from_target_space(
            self.controller, self.target_lookat, Space.Source)
        np.testing.assert_allclose(source, self.source_lookat, rtol=1e-4, atol=1e-3)
        target = camera_lookat_from_target_space(
            self.controller, self.target_lookat, Space.Target)
        np.testing.assert_allclose(target, self.target_lookat, rtol=1e-5, atol=1e-5)
        composite = camera_lookat_from_target_space(
            self.controller, self.target_lookat, Space.Source, view_type=ViewType.Composite)
        np.testing.assert_allclose(composite, self.target_lookat, rtol=1e-5, atol=1e-5)

    def test_match_from_source_aligns_all_panel_cameras(self) -> None:
        """Simulate M on Source: all panels end at corresponding centers."""
        sync = target_space_lookat_for_stos_view(
            _TestCamera(self.source_lookat),
            self.controller,
            Space.Source,
            ViewType.Source,
        )
        source_cam = camera_lookat_from_target_space(self.controller, sync, Space.Source)
        target_cam = camera_lookat_from_target_space(self.controller, sync, Space.Target)
        composite_cam = camera_lookat_from_target_space(
            self.controller, sync, Space.Source, view_type=ViewType.Composite)
        np.testing.assert_allclose(source_cam, self.source_lookat, rtol=1e-4, atol=1e-3)
        np.testing.assert_allclose(target_cam, sync, rtol=1e-5, atol=1e-5)
        np.testing.assert_allclose(composite_cam, sync, rtol=1e-5, atol=1e-5)
        display = display_lookat_for_composite(_TestCamera(composite_cam), self.controller)
        np.testing.assert_allclose(display, sync, rtol=1e-4, atol=1e-3)


class TestCompositePanIgnoresWildInverse(unittest.TestCase):
    """Plain display translate must not rocket when InverseTransform is wild (rigid→RBF)."""

    def test_pan_moves_lookat_by_delta_despite_bad_inverse(self) -> None:
        controller = TransformController(_mesh())
        controller._rbf_prewarm_ready = True
        camera = _TestCamera(np.array([150.0, 200.0], dtype=np.float64))
        before = camera.lookat.copy()
        delta = np.array([3.0, -5.0], dtype=np.float64)
        with patch.object(
                controller, "InverseTransform",
                return_value=np.array([[1.14e8, 1.39e8]], dtype=np.float64)):
            apply_composite_display_pan_delta(camera, controller, delta)
        np.testing.assert_allclose(camera.lookat, before + delta, rtol=1e-5, atol=1e-5)


if __name__ == "__main__":
    unittest.main()
