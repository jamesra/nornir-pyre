"""Unit tests for STOS transform edit policy helpers."""

import unittest

import numpy as np
from nornir_imageregistration.transforms.base import ITargetSpaceControlPointEdit
from nornir_imageregistration.transforms.meshwithrbffallback import MeshWithRBFFallback
from nornir_imageregistration.transforms.transform_type import TransformType

from pyre.interfaces.action import ControlPointAction
from pyre.interfaces.viewtype import ViewType
from pyre.space import Space
from pyre.transform_edit_policy import (
    blocks_control_point_translate_action,
    blocks_layer_translate_action,
    source_panel_control_points_locked,
    source_panel_hint_message,
    rigid_rotation_locked,
    target_panel_manipulation_locked,
)


def _mesh() -> MeshWithRBFFallback:
    points = np.array([
        [10.0, 20.0, 100.0, 200.0],
        [30.0, 40.0, 300.0, 400.0],
        [50.0, 60.0, 500.0, 600.0],
        [70.0, 80.0, 700.0, 800.0],
    ], dtype=np.float32)
    return MeshWithRBFFallback(points)


class _GridLikeTransform(ITargetSpaceControlPointEdit):
    """Minimal stand-in for grid-like target-only control point edits."""

    def UpdateTargetPointsByIndex(self, index, points, *, remove_duplicates=True):
        return index

    def UpdateTargetPointsByPosition(self, old_points, new_points, *, remove_duplicates=True):
        return 0


def _grid() -> _GridLikeTransform:
    return _GridLikeTransform()


class TestTransformEditPolicy(unittest.TestCase):
    """Policy gates for which panels accept layer translate/rotate."""

    def test_rigid_rotation_only_in_composite(self) -> None:
        self.assertFalse(
            rigid_rotation_locked(TransformType.RIGID, ViewType.Composite))
        self.assertTrue(
            rigid_rotation_locked(TransformType.RIGID, ViewType.Target))
        self.assertTrue(
            rigid_rotation_locked(TransformType.RIGID, ViewType.Source))

    def test_rigid_rotation_allowed_for_mesh_warped(self) -> None:
        self.assertFalse(
            rigid_rotation_locked(TransformType.MESH, ViewType.Target))

    def test_target_standalone_locked_for_rigid(self) -> None:
        self.assertTrue(
            target_panel_manipulation_locked(
                TransformType.RIGID, Space.Target, ViewType.Target))
        self.assertFalse(
            target_panel_manipulation_locked(
                TransformType.RIGID, Space.Source, ViewType.Composite))

    def test_blocks_rigid_translate_on_target_panel(self) -> None:
        self.assertTrue(
            blocks_layer_translate_action(
                TransformType.RIGID, Space.Target, ControlPointAction.TRANSLATE, ViewType.Target))

    def test_allows_mesh_control_point_translate_on_source_panel(self) -> None:
        mesh = _mesh()
        self.assertFalse(
            blocks_layer_translate_action(
                TransformType.MESH, Space.Source, ControlPointAction.TRANSLATE, ViewType.Source))
        self.assertFalse(
            source_panel_control_points_locked(mesh, Space.Source, ViewType.Source))
        self.assertFalse(
            blocks_control_point_translate_action(
                mesh, Space.Source, ControlPointAction.TRANSLATE, ViewType.Source))

    def test_blocks_grid_control_point_translate_on_source_panel(self) -> None:
        grid = _grid()
        self.assertTrue(
            source_panel_control_points_locked(grid, Space.Source, ViewType.Source))
        self.assertTrue(
            blocks_control_point_translate_action(
                grid, Space.Source, ControlPointAction.TRANSLATE, ViewType.Source))
        self.assertFalse(
            blocks_control_point_translate_action(
                grid, Space.Target, ControlPointAction.TRANSLATE, ViewType.Target))

    def test_grid_source_panel_hint_mentions_target_view(self) -> None:
        grid = _grid()
        msg = source_panel_hint_message(
            grid, TransformType.GRID, Space.Source, ViewType.Source)
        self.assertIsNotNone(msg)
        assert msg is not None
        self.assertIn("Target", msg)
        self.assertIn("cannot be moved", msg)

    def test_blocks_translate_all_on_target_panel_for_grid(self) -> None:
        self.assertTrue(
            blocks_layer_translate_action(
                TransformType.GRID, Space.Target, ControlPointAction.TRANSLATE_ALL, ViewType.Target))


if __name__ == "__main__":
    unittest.main()
