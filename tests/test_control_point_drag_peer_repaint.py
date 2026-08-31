"""Tests that a control-point drag repaints peer STOS panels, as the rigid drag does.

Peer panels already refresh their GL buffers from OnPointMoved, but a queued
QOpenGLWidget.update() is not serviced while another panel holds the mouse grab, so they
render stale until mouse-up. repaint_peer_stos_gl_panels exists for exactly that reason and
the rigid drag calls it; the control-point drag did not.

These tests drive the real on_mouse_motion with the collaborators it touches stubbed out, so
no Qt widget or GL context is required.
"""

from __future__ import annotations

import inspect
import unittest
from unittest.mock import patch

import numpy as np
from nornir_imageregistration.transforms.rigid import CenteredSimilarity2DTransform

from pyre import common as pyre_common
from pyre.commands.stos.translatecontrolpointcommand import TranslateControlPointCommand
from pyre.commands.stos.translaterigidcommand import ManipulateRigidTransformCommand
from pyre.controllers.transformcontroller import TransformController
from pyre.interfaces.viewtype import ViewType
from pyre.observable import ObservableSet
from pyre.selection_event_data import PointPair
from pyre.space import Space


class _Size:
    def __init__(self, w: int, h: int) -> None:
        self._w, self._h = w, h

    def width(self) -> int:
        return self._w

    def height(self) -> int:
        return self._h


class _Panel:
    """Stands in for the driving QOpenGLWidget."""

    def __init__(self) -> None:
        self.update_calls = 0

    def size(self) -> _Size:
        return _Size(800, 600)

    def update(self) -> None:
        self.update_calls += 1


def _mesh_controller() -> TransformController:
    """A control-point transform, so MovePoint has points to move."""
    points = np.array([[0.0, 0.0, 0.0, 0.0],
                       [0.0, 100.0, 0.0, 100.0],
                       [100.0, 0.0, 100.0, 0.0],
                       [100.0, 100.0, 100.0, 100.0]], dtype=np.float32)
    import nornir_imageregistration
    return TransformController(
        nornir_imageregistration.transforms.MeshWithRBFFallback(points))


class _Drag:
    """Builds a TranslateControlPointCommand without the DI container or a Qt parent."""

    def __init__(self, space: Space = Space.Source,
                 view_type: ViewType = ViewType.Source) -> None:
        self.controller = _mesh_controller()
        self.panel = _Panel()
        self.window_manager = object()

        cmd = object.__new__(TranslateControlPointCommand)
        cmd._parent = self.panel  # `parent` is a read-only property over this
        cmd._transform_controller = self.controller
        cmd._translate_origin = None
        cmd._selected_point_set = ObservableSet([0])
        cmd._space = space
        cmd._window_manager = self.window_manager
        cmd._width, cmd._height = 800, 600
        # Instance attributes shadow the class methods, which keeps the camera and Qt event
        # plumbing out of the test while on_mouse_motion itself stays under test.
        cmd._view_type = lambda: view_type
        self._positions: list[PointPair] = []
        cmd.get_world_positions = lambda event: self._positions.pop(0)
        self.cmd = cmd

    def motion(self, y: float, x: float) -> None:
        point = np.array([y, x], dtype=np.float64)
        self._positions.append(PointPair(target=point, source=point))
        self.cmd.on_mouse_motion(_LeftButtonEvent())


class _LeftButtonEvent:
    """Only buttons() is consulted by on_mouse_motion."""

    @staticmethod
    def buttons():
        from PyQt6.QtCore import Qt
        return Qt.MouseButton.LeftButton


class TestPeersAreRepaintedDuringTheDrag(unittest.TestCase):

    def _drag_and_count(self, drag: _Drag, moves: int) -> list:
        with patch.object(pyre_common, 'repaint_peer_stos_gl_panels') as repaint:
            for i in range(moves):
                drag.motion(10.0 + i, 20.0 + i)
            return repaint.call_args_list

    def test_a_moving_drag_repaints_peers(self) -> None:
        drag = _Drag()
        calls = self._drag_and_count(drag, moves=3)
        # The first motion only seeds the origin, so two of the three move points.
        self.assertEqual(2, len(calls), 'each moving motion should repaint the peers')

    def test_the_driving_panel_is_excluded(self) -> None:
        drag = _Drag()
        calls = self._drag_and_count(drag, moves=2)
        self.assertEqual(1, len(calls))
        _, kwargs = calls[0]
        self.assertIs(drag.panel, kwargs['exclude_gl_panel'],
                      'the driving panel repaints itself via update(); repainting it '
                      'synchronously as well would double the work')

    def test_the_window_manager_is_passed(self) -> None:
        drag = _Drag()
        calls = self._drag_and_count(drag, moves=2)
        args, _ = calls[0]
        self.assertIs(drag.window_manager, args[0])

    def test_the_driving_panel_still_gets_its_own_update(self) -> None:
        drag = _Drag()
        self._drag_and_count(drag, moves=3)
        self.assertEqual(2, drag.panel.update_calls)

    def test_the_seeding_motion_does_not_repaint(self) -> None:
        """The first motion establishes the origin without moving anything."""
        drag = _Drag()
        calls = self._drag_and_count(drag, moves=1)
        self.assertEqual([], calls, 'nothing moved, so there is nothing to repaint')

    def test_every_panel_and_space_repaints(self) -> None:
        """Unlike the rigid path there is no space gate; MovePoint can rewrite either side."""
        for space in (Space.Source, Space.Target):
            for view_type in (ViewType.Source, ViewType.Target, ViewType.Composite):
                with self.subTest(space=space, view=view_type):
                    drag = _Drag(space=space, view_type=view_type)
                    calls = self._drag_and_count(drag, moves=2)
                    self.assertEqual(1, len(calls),
                                     f'{space} on {view_type} left peers stale')


class TestTheRepaintIsLastInTheHandler(unittest.TestCase):
    """The helper pumps the event queue, so a queued motion can re-enter on_mouse_motion."""

    def test_the_repaint_follows_the_state_updates(self) -> None:
        source = inspect.getsource(TranslateControlPointCommand.on_mouse_motion)
        repaint_at = source.index('repaint_peer_stos_gl_panels')
        for earlier in ('MovePoint', '_translate_origin = world_point',
                        'self.parent.update()'):
            with self.subTest(statement=earlier):
                self.assertLess(source.index(earlier), repaint_at,
                                f'{earlier} must settle before the event queue is pumped')

    def test_the_helper_really_pumps_events(self) -> None:
        """If this stops being true the ordering constraint above can be relaxed."""
        source = inspect.getsource(pyre_common.repaint_peer_stos_gl_panels)
        self.assertIn('processEvents', source)


class TestItMatchesTheRigidPath(unittest.TestCase):

    def test_both_drags_call_the_same_helper(self) -> None:
        for command in (TranslateControlPointCommand, ManipulateRigidTransformCommand):
            with self.subTest(command=command.__name__):
                source = inspect.getsource(command.on_mouse_motion)
                self.assertIn('repaint_peer_stos_gl_panels', source)

    def test_both_exclude_the_driving_panel(self) -> None:
        for command in (TranslateControlPointCommand, ManipulateRigidTransformCommand):
            with self.subTest(command=command.__name__):
                source = inspect.getsource(command.on_mouse_motion)
                self.assertIn('exclude_gl_panel=self.parent', source)


if __name__ == '__main__':
    unittest.main()
