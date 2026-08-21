"""Tests for Pyre panel space vs registration control-point column mapping."""

from __future__ import annotations

import copy
import unittest
from unittest.mock import MagicMock, patch

import numpy as np

from nornir_imageregistration.grid_subdivision import ITKGridDivision
from nornir_imageregistration.transforms.gridtransform import GridTransform
from nornir_imageregistration.transforms.meshwithrbffallback import MeshWithRBFFallback

from pyre.commands.stos.translatecontrolpointcommand import TranslateControlPointCommand
from pyre.controllers.transformcontroller import TransformController
from pyre.interfaces.viewtype import ViewType
from pyre.space import Space
from pyre.viewmodels.controlpointmap import ControlPointMap


def _mesh_with_offset() -> MeshWithRBFFallback:
    """Four-point mesh with distinct target and source coordinates."""
    points = np.array([
        [10.0, 20.0, 100.0, 200.0],
        [30.0, 40.0, 300.0, 400.0],
        [50.0, 60.0, 500.0, 600.0],
        [70.0, 80.0, 700.0, 800.0],
    ], dtype=np.float32)
    return MeshWithRBFFallback(points)


def _identity_grid() -> GridTransform:
    """Small grid with aligned source/target points."""
    from nornir_imageregistration.transforms import Rigid

    grid = ITKGridDivision(source_shape=(32, 32), cell_size=(16, 16))
    grid.PopulateTargetPoints(
        Rigid(target_offset=(0.0, 0.0), source_rotation_center=(16.0, 16.0), angle=0.0))
    return GridTransform(grid)


class TestControlPointSpaceMapping(unittest.TestCase):
    """MovePoint/GetPoints/ControlPointMap align Pyre Space with registration columns."""

    def setUp(self) -> None:
        self.controller = TransformController(_mesh_with_offset())

    def test_get_points_source_returns_source_columns(self) -> None:
        source = self.controller.GetPoints(0, space=Space.Source)
        np.testing.assert_allclose(source, [100.0, 200.0])

    def test_get_points_target_returns_target_columns(self) -> None:
        target = self.controller.GetPoints(0, space=Space.Target)
        np.testing.assert_allclose(target, [10.0, 20.0])

    def test_move_point_source_updates_source_points_only(self) -> None:
        before = copy.deepcopy(self.controller.points)
        self.controller.MovePoint(0, ImageDX=2.0, ImageDY=1.0, space=Space.Source)
        after = self.controller.points
        np.testing.assert_allclose(after[0, 2:4], before[0, 2:4] + np.array([1.0, 2.0]))
        np.testing.assert_allclose(after[1:, 2:4], before[1:, 2:4])
        np.testing.assert_allclose(after[:, 0:2], before[:, 0:2])

    def test_move_point_target_updates_target_points_only(self) -> None:
        before = copy.deepcopy(self.controller.points)
        self.controller.MovePoint(1, ImageDX=-3.0, ImageDY=4.0, space=Space.Target)
        after = self.controller.points
        np.testing.assert_allclose(after[:, 2:4], before[:, 2:4])
        np.testing.assert_allclose(after[1, 0:2], before[1, 0:2] + np.array([4.0, -3.0]))
        np.testing.assert_allclose(after[0, 0:2], before[0, 0:2])
        np.testing.assert_allclose(after[2:, 0:2], before[2:, 0:2])

    def test_controlpointmap_source_uses_source_points(self) -> None:
        cmap = ControlPointMap(self.controller, Space.Source)
        np.testing.assert_allclose(cmap.points, self.controller.SourcePoints)

    def test_controlpointmap_target_uses_target_points(self) -> None:
        cmap = ControlPointMap(self.controller, Space.Target)
        np.testing.assert_allclose(cmap.points, self.controller.TargetPoints)

    def test_draw_tween_matches_hit_test_space(self) -> None:
        self.assertEqual(ControlPointMap.draw_tween_for_pyre_space(Space.Source), 0.0)
        self.assertEqual(ControlPointMap.draw_tween_for_pyre_space(Space.Target), 1.0)

    def test_shader_tween_draws_registration_columns(self) -> None:
        """Shader tween 0 selects SourcePoints; 1 selects TargetPoints."""
        source_tween = ControlPointMap.shader_tween_for_panel_space(Space.Source)
        target_tween = ControlPointMap.shader_tween_for_panel_space(Space.Target)
        self.assertEqual(source_tween, 0.0)
        self.assertEqual(target_tween, 1.0)
        cmap_source = ControlPointMap(self.controller, Space.Source)
        cmap_target = ControlPointMap(self.controller, Space.Target)
        np.testing.assert_allclose(cmap_source.points, self.controller.SourcePoints)
        np.testing.assert_allclose(cmap_target.points, self.controller.TargetPoints)


class TestGridControlPointDragDirection(unittest.TestCase):
    """Grid CP drags must move TargetPoints in the same direction as the mouse."""

    def test_grid_move_point_target_follows_positive_delta(self) -> None:
        controller = TransformController(_identity_grid())
        before = np.array(controller.TargetPoints[0], copy=True)
        controller.MovePoint(0, ImageDX=5.0, ImageDY=3.0, space=Space.Target)
        after = controller.TargetPoints[0]
        np.testing.assert_allclose(after, before + np.array([3.0, 5.0]))

    def test_grid_source_space_fallback_moves_target_same_direction(self) -> None:
        """Grid has no source-point edit; Source MovePoint maps into TargetPoints."""
        controller = TransformController(_identity_grid())
        before = np.array(controller.TargetPoints[0], copy=True)
        source_before = np.array(controller.SourcePoints[0], copy=True)
        # Positive ImageDX/ImageDY must move the editable target point +Y/+X, not invert.
        controller.MovePoint(0, ImageDX=5.0, ImageDY=3.0, space=Space.Source)
        after = controller.TargetPoints[0]
        np.testing.assert_allclose(after, before + np.array([3.0, 5.0]), atol=1e-3)
        np.testing.assert_allclose(controller.SourcePoints[0], source_before)

    def test_composite_translate_command_edits_target_space(self) -> None:
        cmd = object.__new__(TranslateControlPointCommand)
        cmd._space = Space.Source
        cmd._transform_controller = TransformController(_identity_grid())
        cmd._view_type = MagicMock(return_value=ViewType.Composite)  # type: ignore[method-assign]
        self.assertEqual(cmd._edit_space_for_translate(), Space.Target)

    def test_composite_activate_begins_interactive_edit_in_target_space(self) -> None:
        from pyre.commands.navigationcommandbase import NavigationCommandBase

        cmd = object.__new__(TranslateControlPointCommand)
        cmd._space = Space.Source
        controller = MagicMock()
        cmd._transform_controller = controller
        cmd._view_type = MagicMock(return_value=ViewType.Composite)  # type: ignore[method-assign]
        cmd._selected_point_set = set()
        cmd._command_points = {0}
        with patch.object(NavigationCommandBase, "activate", lambda self: None):
            TranslateControlPointCommand.activate(cmd)
        controller.begin_interactive_edit.assert_called_once_with(
            Space.Target, view_type=ViewType.Composite)


if __name__ == "__main__":
    unittest.main()
