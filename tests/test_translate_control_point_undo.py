"""Multi-point (and single-point) translate gestures push one Ctrl+Z undo entry."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

import numpy as np

import nornir_imageregistration
import pyre
from pyre.commands.stos.translatecontrolpointcommand import TranslateControlPointCommand
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


def _translate_command(
        controller: TransformController,
        indices: set[int],
        history: CommandHistory,
) -> TranslateControlPointCommand:
    cmd = object.__new__(TranslateControlPointCommand)
    cmd._parent = MagicMock()
    cmd._transform_controller = controller
    cmd._translate_origin = None
    cmd._selected_point_set = ObservableSet(list(indices))
    cmd._command_points = set(indices)
    cmd._space = Space.Target
    # Match production: snapshot before begin_interactive_edit (virtual points).
    cmd._original_points = controller.copy_points()
    cmd._history_manager = history
    cmd._command_completed_callbacks = []
    cmd._status = pyre.CommandStatus.Active
    cmd._result = pyre.CommandResult.Unknown
    # Avoid Qt event rebinding; this test only covers undo snapshot on execute.
    cmd.unsubscribe_to_parent = lambda: None  # type: ignore[method-assign]
    controller.begin_interactive_edit(Space.Target)
    return cmd


class TestTranslateControlPointUndo(unittest.TestCase):
    def test_multi_point_drag_is_undoable(self) -> None:
        controller = _mesh_controller()
        history = CommandHistory()
        before = controller.copy_points()
        cmd = _translate_command(controller, {0, 1}, history)

        controller.MovePoint([0, 1], ImageDX=5.0, ImageDY=3.0, space=Space.Target)
        cmd.execute()
        self.assertEqual(history.HistoryDepth, 1)
        self.assertFalse(np.allclose(controller.copy_points(), before))

        history.Undo()
        np.testing.assert_allclose(controller.copy_points(), before)

    def test_noop_release_does_not_push_history(self) -> None:
        controller = _mesh_controller()
        history = CommandHistory()
        cmd = _translate_command(controller, {0, 1}, history)
        cmd.execute()
        self.assertEqual(history.HistoryDepth, 0)


if __name__ == "__main__":
    unittest.main()
