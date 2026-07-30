"""Tests for composite display-space helpers (rigid and mesh/grid)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

import numpy as np
from nornir_imageregistration.transforms.meshwithrbffallback import MeshWithRBFFallback
from nornir_imageregistration.transforms import Rigid

from pyre.controllers.transformcontroller import TransformController
from pyre.viewmodels.controlpointmap import ControlPointMap
from pyre.interfaces.viewtype import ViewType
from pyre.space import Space
from pyre.views.composite_display import (
    composite_control_point_draw_rows,
    composite_tile_cull_rect,
    display_lookat_for_composite,
    lookat_from_display_position,
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
        self.camera = MagicMock()
        self.camera.lookat = np.array([20.0, 30.0], dtype=np.float64)

    def test_display_lookat_is_forward_of_camera_lookat(self) -> None:
        expected = np.squeeze(self.controller.Transform(self.camera.lookat.reshape(1, 2)))
        actual = display_lookat_for_composite(self.camera, self.controller)
        np.testing.assert_allclose(actual, expected, rtol=1e-5, atol=1e-5)

    def test_world_point_pair_round_trips_mesh(self) -> None:
        display = np.array([150.0, 250.0], dtype=np.float64)
        self.camera.image_coords_for_lookat.return_value = display
        pair = world_point_pair_for_composite_mouse(self.camera, self.controller, 100.0, 150.0)
        self.assertIsNotNone(pair)
        assert pair is not None
        roundtrip = np.squeeze(self.controller.Transform(pair.source.reshape(1, 2)))
        np.testing.assert_allclose(roundtrip, pair.target, rtol=1e-4, atol=1e-3)

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
    """Ending a composite rigid translate must keep target-display framing."""

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

        # Mimic execute(): capture while frozen, end gesture, rebase lookat.
        display_frozen = display_lookat_for_composite(camera, controller)
        np.testing.assert_allclose(display_frozen, display_before, atol=1e-5)
        controller.end_interactive_edit()
        camera.lookat = lookat_from_display_position(controller, display_frozen)

        display_after = display_lookat_for_composite(camera, controller)
        np.testing.assert_allclose(display_after, display_before, atol=1e-4)
        # Without rebase, live Transform(old lookat) would have jumped with the translate.
        unbased = _transform_without_rebase(controller, np.array([40.0, 50.0], dtype=np.float64))
        self.assertFalse(np.allclose(unbased, display_before, atol=1.0))


def _transform_without_rebase(
        controller: TransformController, source_lookat: np.ndarray) -> np.ndarray:
    return np.squeeze(np.asarray(controller.Transform(source_lookat.reshape(1, 2)), dtype=np.float64))


if __name__ == "__main__":
    unittest.main()
