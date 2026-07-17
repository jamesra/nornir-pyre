"""Unit tests for STOS transform edit policy helpers."""

import unittest

from nornir_imageregistration.transforms.transform_type import TransformType

from pyre.interfaces.viewtype import ViewType
from pyre.space import Space
from pyre.interfaces.action import ControlPointAction
from pyre.transform_edit_policy import (
    blocks_layer_translate_action,
    fixed_image_manipulation_locked,
    rigid_rotation_locked,
)


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

    def test_fixed_standalone_still_locked_for_rigid(self) -> None:
        self.assertTrue(
            fixed_image_manipulation_locked(
                TransformType.RIGID, Space.Source, ViewType.Source))
        self.assertFalse(
            fixed_image_manipulation_locked(
                TransformType.RIGID, Space.Source, ViewType.Composite))

    def test_blocks_rigid_translate_on_fixed_panel(self) -> None:
        self.assertTrue(
            blocks_layer_translate_action(
                TransformType.RIGID, Space.Source, ControlPointAction.TRANSLATE, ViewType.Source))

    def test_allows_mesh_control_point_translate_on_fixed_panel(self) -> None:
        self.assertFalse(
            blocks_layer_translate_action(
                TransformType.MESH, Space.Source, ControlPointAction.TRANSLATE, ViewType.Source))
        self.assertFalse(
            blocks_layer_translate_action(
                TransformType.GRID, Space.Source, ControlPointAction.TRANSLATE, ViewType.Source))

    def test_blocks_translate_all_on_fixed_panel_for_grid(self) -> None:
        self.assertTrue(
            blocks_layer_translate_action(
                TransformType.GRID, Space.Source, ControlPointAction.TRANSLATE_ALL, ViewType.Source))


if __name__ == "__main__":
    unittest.main()
