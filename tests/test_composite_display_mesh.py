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
    display_lookat_for_composite,
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

    def test_composite_controlpointmap_uses_display_fixed_positions(self) -> None:
        cmap = ControlPointMap(self.controller, Space.Source, view_type=ViewType.Composite)
        expected = np.asarray(self.controller.Transform(self.controller.TargetPoints), dtype=np.float64)
        np.testing.assert_allclose(cmap.points, expected, atol=1e-10)

    def test_composite_control_point_draw_rows_transforms_fixed_columns(self) -> None:
        rows = composite_control_point_draw_rows(self.controller, Space.Source)
        self.assertIsNotNone(rows)
        assert rows is not None
        expected = np.asarray(self.controller.Transform(self.controller.TargetPoints), dtype=np.float64)
        np.testing.assert_allclose(rows[:, 0:2], expected, atol=1e-10)

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


if __name__ == "__main__":
    unittest.main()
