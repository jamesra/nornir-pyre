"""Shift+right-click on an unselected point deletes only that point.

Adding a point leaves it selected. Shift+right-click on another point then deleted the
selection plus the clicked point, so deleting the first of two new points removed both
(2026-11-03). Clicking a selected point still deletes the whole selection, matching
drag-a-selected-point-moves-the-group.
"""
from __future__ import annotations

import unittest

import nornir_imageregistration
import numpy as np
from nornir_imageregistration.computational_lib import HasCupy
from pyre.commands.stos.actionmaphelpers import mesh_can_delete, points_to_delete
from pyre.commands.stos.deletecontrolpointcommand import DeleteControlPointCommand
from pyre.commands.transform_undo import save_points_undo
from pyre.controllers.transformcontroller import TransformController
from pyre.observable import ObservableSet
from pyre.selection_event_data import SelectionEventData
from pyre.state.managers.command_history import CommandHistory


def _points() -> np.ndarray:
    fixed = np.array([[i * 100.0, j * 100.0] for i in range(3) for j in range(3)])
    return np.hstack([fixed, fixed + np.array([5.0, -3.0])])


def _delete(controller: TransformController, selected: set[int], clicked: set[int]) -> ObservableSet[int]:
    selection = ObservableSet(selected)
    DeleteControlPointCommand(
        selection, clicked,
        transform_controller=controller, history_manager=CommandHistory()).activate()
    return selection


class TestPointsToDelete(unittest.TestCase):

    def test_unselected_click_deletes_only_the_clicked_point(self):
        self.assertEqual(points_to_delete({8}, {0}), {0})

    def test_selected_click_deletes_the_selection(self):
        self.assertEqual(points_to_delete({2, 5}, {5}), {2, 5})

    def test_delete_key_deletes_the_selection(self):
        self.assertEqual(points_to_delete({2, 5}, set()), {2, 5})

    def test_can_delete_counts_only_the_points_that_go(self):
        event = object.__new__(SelectionEventData)
        event.existing_selections = ObservableSet({1, 2, 3, 4, 5})
        # 9 points: deleting the clicked unselected point leaves 8; the union would leave 3.
        self.assertTrue(mesh_can_delete(9, event, {0}))
        self.assertFalse(mesh_can_delete(7, event, {1}))


class _DeleteCases:

    def _model(self):
        return nornir_imageregistration.transforms.MeshWithRBFFallback(_points())

    def test_deleting_the_first_of_two_added_points_keeps_the_second(self):
        controller = TransformController(self._model())
        first = controller.TryAddPoint(450.0, 450.0)
        second = controller.TryAddPoint(-150.0, 450.0)
        selected = {int(second)}
        expected = np.delete(nornir_imageregistration.EnsureNumpyArray(controller.copy_points()), int(first), axis=0)

        _delete(controller, selected, {int(first)})

        self.assertEqual(controller.NumPoints, 10)
        np.testing.assert_allclose(
            nornir_imageregistration.EnsureNumpyArray(controller.copy_points()), expected)

    def test_delete_is_undoable(self):
        controller = TransformController(self._model())
        before = nornir_imageregistration.EnsureNumpyArray(controller.copy_points())
        history = CommandHistory()
        selection = ObservableSet({4})
        DeleteControlPointCommand(
            selection, {4}, transform_controller=controller, history_manager=history).activate()
        self.assertEqual(controller.NumPoints, 8)
        history.Undo()
        np.testing.assert_allclose(nornir_imageregistration.EnsureNumpyArray(controller.copy_points()), before)


class TestDeleteMesh(_DeleteCases, unittest.TestCase):
    pass


class TestDeleteRbf(_DeleteCases, unittest.TestCase):

    def _model(self):
        points = _points()
        return nornir_imageregistration.transforms.TwoWayRBFWithLinearCorrection(points[:, 2:], points[:, :2])


@unittest.skipUnless(HasCupy(), "requires CuPy")
class TestDeleteGpuMesh(_DeleteCases, unittest.TestCase):

    def _model(self):
        import cupy as cp
        return nornir_imageregistration.transforms.MeshWithRBFFallback_GPUComponent(cp.asarray(_points()))

    def test_undo_snapshot_accepts_device_points(self):
        import cupy as cp
        history = CommandHistory()
        save_points_undo(history, lambda _p: None, cp.asarray(_points()))
        self.assertEqual(history.HistoryDepth, 1)


if __name__ == '__main__':
    unittest.main()
