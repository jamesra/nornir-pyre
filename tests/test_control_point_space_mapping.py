"""Tests for Pyre panel space vs registration control-point column mapping."""

from __future__ import annotations

import copy
import unittest

import numpy as np

import nornir_imageregistration.transforms
from nornir_imageregistration.transforms.meshwithrbffallback import MeshWithRBFFallback

from pyre.controllers.transformcontroller import TransformController
from pyre.space import Space
from pyre.viewmodels.controlpointmap import ControlPointMap


def _mesh_with_offset() -> MeshWithRBFFallback:
    """Four-point mesh with distinct fixed (target) and warped (source) coordinates."""
    points = np.array([
        [10.0, 20.0, 100.0, 200.0],
        [30.0, 40.0, 300.0, 400.0],
        [50.0, 60.0, 500.0, 600.0],
        [70.0, 80.0, 700.0, 800.0],
    ], dtype=np.float32)
    return MeshWithRBFFallback(points)


class TestControlPointSpaceMapping(unittest.TestCase):
    """MovePoint/GetPoints/ControlPointMap use Pyre space (Source=fixed, Target=warped)."""

    def setUp(self) -> None:
        self.controller = TransformController(_mesh_with_offset())

    def test_get_points_source_returns_fixed_target_columns(self) -> None:
        fixed = self.controller.GetPoints(0, space=Space.Source)
        np.testing.assert_allclose(fixed, [10.0, 20.0])

    def test_get_points_target_returns_warped_source_columns(self) -> None:
        warped = self.controller.GetPoints(0, space=Space.Target)
        np.testing.assert_allclose(warped, [100.0, 200.0])

    def test_move_point_source_updates_target_points_only(self) -> None:
        before = copy.deepcopy(self.controller.points)
        self.controller.MovePoint(0, ImageDX=2.0, ImageDY=1.0, space=Space.Source)
        after = self.controller.points
        np.testing.assert_allclose(after[0, 0:2], before[0, 0:2] + np.array([1.0, 2.0]))
        np.testing.assert_allclose(after[1:, 0:2], before[1:, 0:2])
        np.testing.assert_allclose(after[:, 2:4], before[:, 2:4])

    def test_move_point_target_updates_source_points_only(self) -> None:
        before = copy.deepcopy(self.controller.points)
        self.controller.MovePoint(1, ImageDX=-3.0, ImageDY=4.0, space=Space.Target)
        after = self.controller.points
        np.testing.assert_allclose(after[:, 0:2], before[:, 0:2])
        np.testing.assert_allclose(after[1, 2:4], before[1, 2:4] + np.array([4.0, -3.0]))
        np.testing.assert_allclose(after[0, 2:4], before[0, 2:4])
        np.testing.assert_allclose(after[2:, 2:4], before[2:, 2:4])

    def test_controlpointmap_source_uses_target_points(self) -> None:
        cmap = ControlPointMap(self.controller, Space.Source)
        np.testing.assert_allclose(cmap.points, self.controller.TargetPoints)

    def test_controlpointmap_target_uses_source_points(self) -> None:
        cmap = ControlPointMap(self.controller, Space.Target)
        np.testing.assert_allclose(cmap.points, self.controller.SourcePoints)

    def test_draw_tween_matches_hit_test_space(self) -> None:
        self.assertEqual(ControlPointMap.draw_tween_for_pyre_space(Space.Source), 1.0)
        self.assertEqual(ControlPointMap.draw_tween_for_pyre_space(Space.Target), 0.0)


if __name__ == "__main__":
    unittest.main()
