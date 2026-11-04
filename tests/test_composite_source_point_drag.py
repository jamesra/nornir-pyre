"""Transform Settings "Composite drag moves: Source point" slides the warped image under a still point.

A composite drag normally edits target points, so the point follows the cursor over the
image. With the setting on Source the target point stays put and the source point moves
so the image content follows the cursor. The cursor delta is mapped to source space with
the local target -> source map from before the drag, so the edit does not feed back into
its own mapping. Grid transforms only edit target points and keep the Target behaviour.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import nornir_imageregistration
import numpy as np
from nornir_imageregistration.transforms import MeshWithRBFFallback
from pyre.commands.navigationcommandbase import NavigationCommandBase
from pyre.commands.stos.translatecontrolpointcommand import TranslateControlPointCommand
from pyre.controllers.transformcontroller import TransformController
from pyre.interfaces.viewtype import ViewType
from pyre.settings import AppSettings, StosSettings
from pyre.space import Space

_SCALE = np.array([[2.0, 0.0], [0.0, 0.5]])  # target = source @ _SCALE + _OFFSET
_OFFSET = np.array([10.0, -4.0])


def _scaled_mesh() -> MeshWithRBFFallback:
    source = np.array([[y, x] for y in (0.0, 100.0, 200.0) for x in (0.0, 100.0, 200.0)])
    return MeshWithRBFFallback(np.hstack((source @ _SCALE + _OFFSET, source)))


def _grid():
    from nornir_imageregistration.transforms import GridTransform, Rigid
    grid = nornir_imageregistration.ITKGridDivision(source_shape=(32, 32), cell_size=(16, 16))
    grid.PopulateTargetPoints(Rigid(target_offset=(0.0, 0.0), source_rotation_center=(16.0, 16.0), angle=0.0))
    return GridTransform(grid)


def _command(controller: TransformController, points: set[int], drag_space: str) -> TranslateControlPointCommand:
    cmd = object.__new__(TranslateControlPointCommand)
    cmd._space = Space.Source
    cmd._transform_controller = controller
    cmd._view_type = MagicMock(return_value=ViewType.Composite)  # type: ignore[method-assign]
    cmd._command_points = set(points)
    cmd._selected_point_set = set()
    cmd._composite_drag_space = drag_space
    cmd._target_to_source_jacobian = None
    return cmd


def _drag(cmd: TranslateControlPointCommand, display_delta_yx) -> None:
    dy, dx = cmd._edit_delta(np.asarray(display_delta_yx, dtype=np.float64))
    cmd._transform_controller.MovePoint(list(cmd._command_points), dx, dy, space=cmd._edit_space_for_translate())


class TestCompositeSourceDrag(unittest.TestCase):

    def test_source_setting_edits_source_points_on_a_mesh(self):
        cmd = _command(TransformController(_scaled_mesh()), {4}, "source")
        self.assertEqual(cmd._edit_space_for_translate(), Space.Source)

    def test_target_setting_keeps_target_edits(self):
        cmd = _command(TransformController(_scaled_mesh()), {4}, "target")
        self.assertEqual(cmd._edit_space_for_translate(), Space.Target)

    def test_grid_ignores_the_source_setting(self):
        cmd = _command(TransformController(_grid()), {4}, "source")
        self.assertEqual(cmd._edit_space_for_translate(), Space.Target)

    def test_point_stays_and_image_follows_the_cursor(self):
        controller = TransformController(_scaled_mesh())
        targets_before = np.array(controller.TargetPoints, copy=True)
        sources_before = np.array(controller.SourcePoints, copy=True)
        cmd = _command(controller, set(range(9)), "source")
        delta = np.array([6.0, -3.0])

        for step in (delta / 3,) * 3:
            _drag(cmd, step)

        np.testing.assert_allclose(controller.TargetPoints, targets_before, atol=1e-4)
        # Every source point moved by -S^-1 d, so image content now lands d further along.
        np.testing.assert_allclose(
            controller.SourcePoints, sources_before - delta @ np.linalg.inv(_SCALE), atol=1e-3)
        moved_content = nornir_imageregistration.EnsureNumpyArray(controller.Transform(sources_before[4:5]))
        np.testing.assert_allclose(moved_content[0], targets_before[4] + delta, atol=1e-3)

    def test_single_point_drag_moves_content_toward_the_cursor(self):
        controller = TransformController(_scaled_mesh())
        source_center = np.array(controller.SourcePoints[4], copy=True)
        target_center = np.array(controller.TargetPoints[4], copy=True)
        cmd = _command(controller, {4}, "source")
        delta = np.array([8.0, 2.0])
        _drag(cmd, delta)

        np.testing.assert_allclose(controller.TargetPoints[4], target_center, atol=1e-4)
        content = nornir_imageregistration.EnsureNumpyArray(controller.Transform(source_center[None, :]))[0]
        moved = content - target_center
        # Moving one vertex reshapes its triangles, so the content lands close to, not exactly at, the cursor.
        self.assertGreater(float(np.dot(moved, delta) / np.dot(delta, delta)), 0.9)
        self.assertLess(float(np.linalg.norm(moved - delta)), 0.1 * float(np.linalg.norm(delta)))

    def test_mapping_is_frozen_at_drag_start(self):
        controller = TransformController(_scaled_mesh())
        cmd = _command(controller, {4}, "source")
        _drag(cmd, (5.0, 5.0))
        first = np.array(cmd._target_to_source_jacobian, copy=True)
        _drag(cmd, (5.0, 5.0))
        np.testing.assert_array_equal(cmd._target_to_source_jacobian, first)
        np.testing.assert_allclose(first, np.linalg.inv(_SCALE).T, atol=1e-4)

    def test_activate_begins_a_source_space_edit(self):
        controller = TransformController(_scaled_mesh())
        cmd = _command(controller, {4}, "source")
        begin = MagicMock()
        with (patch.object(NavigationCommandBase, "activate", lambda self: None),
              patch.object(controller, "begin_interactive_edit", begin)):
            TranslateControlPointCommand.activate(cmd)
        begin.assert_called_once_with(Space.Source, view_type=ViewType.Composite)
        self.assertIsNotNone(cmd._target_to_source_jacobian)


class TestCompositeDragSetting(unittest.TestCase):

    def test_default_is_target(self):
        self.assertEqual("target", AppSettings().stos.composite_point_drag_space)

    def test_round_trips(self):
        settings = AppSettings(stos=StosSettings(composite_point_drag_space="source"))
        restored = AppSettings.model_validate_json(settings.model_dump_json())
        self.assertEqual("source", restored.stos.composite_point_drag_space)


if __name__ == '__main__':
    unittest.main()
