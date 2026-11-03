"""DefaultTransformCommand must rebind action maps when the transform type changes."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from nornir_imageregistration.transforms.transform_type import TransformType

from pyre.commands.defaulttransformcommand import DefaultTransformCommand
from pyre.commands.stos.rigidtransformactionmap import RigidTransformActionMap
from pyre.commands.stos.triangulationtransformactionmap import TriangulationTransformActionMap
from pyre.interfaces.action import ControlPointAction


class TestDefaultTransformCommandRebind(unittest.TestCase):
    def test_ensure_maps_rebind_when_type_changes(self) -> None:
        """Rigid Space refine must not stick after the model becomes RBF/mesh."""
        command = object.__new__(DefaultTransformCommand)
        command._transform_controller = SimpleNamespace(type=TransformType.RIGID, TransformModel=object())
        command._bound_transform_type = TransformType.RIGID
        command._space = MagicMock()
        command._view_type = MagicMock(return_value=None)
        command._controlpointmap_manager = MagicMock()
        command._action_command_map_by_type = {
            TransformType.RIGID: {ControlPointAction.REFINE_RIGID: object()},
            TransformType.RBF: {ControlPointAction.REGISTER: object()},
        }
        rigid_map = MagicMock(spec=RigidTransformActionMap)
        rbf_map = MagicMock(spec=TriangulationTransformActionMap)
        command._get_transform_action_map_dict = MagicMock(return_value={
            TransformType.RIGID: MagicMock(return_value=rigid_map),
            TransformType.RBF: MagicMock(return_value=rbf_map),
        })
        command._actionmap = rigid_map
        command._action_to_command = command._action_command_map_by_type[TransformType.RIGID]

        command._transform_controller.type = TransformType.RBF
        command._transform_controller.TransformModel = MagicMock()  # not IControlPoints
        # isinstance check uses real IControlPoints; MagicMock is not, so factory() path.
        command._ensure_maps_match_transform_type()

        self.assertEqual(command._bound_transform_type, TransformType.RBF)
        self.assertIs(command._actionmap, rbf_map)
        self.assertIn(ControlPointAction.REGISTER, command._action_to_command)
        self.assertNotIn(ControlPointAction.REFINE_RIGID, command._action_to_command)

    def test_ensure_maps_noop_when_type_unchanged(self) -> None:
        command = object.__new__(DefaultTransformCommand)
        command._transform_controller = SimpleNamespace(type=TransformType.MESH)
        command._bound_transform_type = TransformType.MESH
        command._rebind_maps_for_current_transform_type = MagicMock()

        command._ensure_maps_match_transform_type()

        command._rebind_maps_for_current_transform_type.assert_not_called()


if __name__ == "__main__":
    unittest.main()
