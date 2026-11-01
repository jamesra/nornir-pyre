"""Ctrl+Z coverage for synchronous transform edit commands."""

from __future__ import annotations

import copy
import unittest
from unittest.mock import MagicMock

import numpy as np

import nornir_imageregistration
from nornir_imageregistration.transforms import Rigid
from pyre.commands.callcontrolpointtomousecommand import CallControlPointToMouseCommand
from pyre.commands.stos.deletecontrolpointcommand import DeleteControlPointCommand
from pyre.commands.stos.translaterigidcommand import ManipulateRigidTransformCommand
from pyre.commands.transform_undo import (
    rigid_state_changed,
    save_points_undo,
    save_rigid_undo,
)
from pyre.controllers.transformcontroller import TransformController
from pyre.observable import ObservableSet
from pyre.space import Space
from pyre.state.managers.command_history import CommandHistory


def _mesh_controller() -> TransformController:
    points = np.array(
        [[0.0, 0.0, 0.0, 0.0],
         [10.0, 0.0, 10.0, 0.0],
         [0.0, 10.0, 0.0, 10.0],
         [10.0, 10.0, 10.0, 10.0]],
        dtype=np.float64,
    )
    return TransformController(
        nornir_imageregistration.transforms.MeshWithRBFFallback(points))


class TestTransformUndoHelpers(unittest.TestCase):
    def test_save_points_undo_restores(self) -> None:
        controller = _mesh_controller()
        history = CommandHistory()
        before = controller.copy_points()
        save_points_undo(history, controller.SetPoints, before)
        controller.MovePoint(0, ImageDX=4.0, ImageDY=2.0, space=Space.Target)
        history.Undo()
        np.testing.assert_allclose(controller.copy_points(), before)

    def test_save_rigid_undo_restores(self) -> None:
        controller = TransformController(Rigid((0.0, 0.0), (0.0, 0.0), angle=0.0))
        history = CommandHistory()
        model = controller.TransformModel
        assert isinstance(model, Rigid)
        before = model.GetRigidState()
        save_rigid_undo(history, controller, before)
        model.TranslateFixed((5.0, 3.0))
        self.assertTrue(rigid_state_changed(before, model.GetRigidState()))
        history.Undo()
        after = model.GetRigidState()
        self.assertFalse(rigid_state_changed(before, after))


class TestDeleteControlPointUndo(unittest.TestCase):
    def test_delete_is_undoable(self) -> None:
        controller = _mesh_controller()
        history = CommandHistory()
        before = controller.copy_points()
        selection = ObservableSet([3])
        cmd = object.__new__(DeleteControlPointCommand)
        cmd._selected_points = selection
        cmd._transform_controller = controller
        cmd._history_manager = history
        cmd._original_points = before
        cmd._command_completed_callbacks = []
        import pyre
        cmd._status = pyre.CommandStatus.Active
        cmd._result = pyre.CommandResult.Unknown

        cmd.execute()
        self.assertEqual(controller.NumPoints, 3)
        history.Undo()
        np.testing.assert_allclose(controller.copy_points(), before)


class TestCallControlPointToMouseUndo(unittest.TestCase):
    def test_call_to_mouse_is_undoable(self) -> None:
        controller = _mesh_controller()
        history = CommandHistory()
        before = controller.copy_points()
        cmd = object.__new__(CallControlPointToMouseCommand)
        cmd._selected_points = ObservableSet([0])
        cmd._selected_point = 0
        cmd._transform_controller = controller
        cmd._history_manager = history
        cmd._original_points = before
        cmd._space = Space.Target
        cmd._mouse_position = np.array([20.0, 30.0], dtype=np.float64)
        cmd._command_completed_callbacks = []
        import pyre
        cmd._status = pyre.CommandStatus.Active
        cmd._result = pyre.CommandResult.Unknown

        cmd.execute()
        self.assertFalse(np.allclose(controller.copy_points(), before))
        history.Undo()
        np.testing.assert_allclose(controller.copy_points(), before)


class TestManipulateRigidUndo(unittest.TestCase):
    def test_execute_pushes_rigid_undo(self) -> None:
        controller = TransformController(Rigid((0.0, 0.0), (0.0, 0.0), angle=0.0))
        history = CommandHistory()
        model = controller.TransformModel
        assert isinstance(model, Rigid)
        before = model.GetRigidState()

        cmd = object.__new__(ManipulateRigidTransformCommand)
        cmd._transform_controller = controller
        cmd._original_state = copy.deepcopy(before)
        cmd._history_manager = history
        cmd._space = Space.Target
        cmd._camera = MagicMock()
        cmd._command_completed_callbacks = []
        import pyre
        cmd._status = pyre.CommandStatus.Active
        cmd._result = pyre.CommandResult.Unknown
        cmd._end_interactive_edit_preserving_composite_display = lambda: None
        cmd.unsubscribe_to_parent = lambda: None  # type: ignore[method-assign]

        model.TranslateFixed((7.0, 1.0))
        cmd.execute()
        self.assertEqual(history.HistoryDepth, 1)
        history.Undo()
        self.assertFalse(rigid_state_changed(before, model.GetRigidState()))


if __name__ == "__main__":
    unittest.main()
