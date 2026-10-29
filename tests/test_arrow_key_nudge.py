"""Arrow-key nudge for control-point and rigid translate commands.

Both commands nudge with the arrow keys: one pixel per press, x5 with Shift,
x25 with Ctrl (x125 with both). The step is (dy, dx) in the command's space:
Up is +Y, Down -Y, Right +X, Left -X. The control-point command passes it to
``MovePoint`` as (dx, dy); the rigid command negates it on the Source panel and
passes the (dy, dx) list to ``Translate``.

``_reference_nudge_yx`` is a copy of the inline logic both commands carried
before it moved to ``pyre.commands.extensions.arrow_key_nudge_yx``.
"""

from __future__ import annotations

import unittest
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st
from nornir_imageregistration.transforms import TransformType
from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QKeyEvent
from pyre.commands.extensions import arrow_key_nudge_yx
from pyre.commands.stos.translatecontrolpointcommand import TranslateControlPointCommand
from pyre.commands.stos.translaterigidcommand import ManipulateRigidTransformCommand
from pyre.interfaces.viewtype import ViewType
from pyre.space import Space

_ARROW_KEYS = (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down)
_OTHER_KEYS = (Qt.Key.Key_A, Qt.Key.Key_Space, Qt.Key.Key_Escape, Qt.Key.Key_PageUp)


def _reference_nudge_yx(event: QKeyEvent) -> list[int] | None:
    """The pre-refactor inline nudge logic, kept verbatim as the oracle."""
    keycode = event.key()
    if not (keycode == Qt.Key.Key_Left or
            keycode == Qt.Key.Key_Right or
            keycode == Qt.Key.Key_Up or
            keycode == Qt.Key.Key_Down):
        return None

    multiplier = 1
    if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
        multiplier *= 5
    if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
        multiplier *= 25

    delta = [0, 0]
    if keycode == Qt.Key.Key_Left:
        delta = [0, -1]
    elif keycode == Qt.Key.Key_Right:
        delta = [0, 1]
    elif keycode == Qt.Key.Key_Up:
        delta = [1, 0]
    elif keycode == Qt.Key.Key_Down:
        delta = [-1, 0]

    delta[0] *= multiplier
    delta[1] *= multiplier
    return delta


@st.composite
def _key_events(draw: st.DrawFn, keys: tuple[Qt.Key, ...] = _ARROW_KEYS + _OTHER_KEYS) -> QKeyEvent:
    """A key press for one of ``keys`` with any mix of Shift, Ctrl, Alt and Meta."""
    key = draw(st.sampled_from(keys))
    modifiers = Qt.KeyboardModifier.NoModifier
    for flag in (Qt.KeyboardModifier.ShiftModifier, Qt.KeyboardModifier.ControlModifier,
                 Qt.KeyboardModifier.AltModifier, Qt.KeyboardModifier.MetaModifier):
        if draw(st.booleans()):
            modifiers |= flag
    return QKeyEvent(QEvent.Type.KeyPress, key, modifiers)


class _RecordingController:
    """Stands in for TransformController; records the nudge calls."""

    type: TransformType

    def __init__(self, transform_type: TransformType = TransformType.RIGID) -> None:
        self.type = transform_type
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def MovePoint(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append(("MovePoint", args, kwargs))

    def Translate(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append(("Translate", args, kwargs))


def _control_point_command(controller: _RecordingController, edit_space: Space,
                           highlighted: int | None = 0) -> TranslateControlPointCommand:
    """Build the command without the Qt/DI machinery, as tests/test_rigid_drag_cancel does."""
    cmd = object.__new__(TranslateControlPointCommand)
    cmd._transform_controller = controller  # type: ignore[assignment]
    cmd._selected_point_set = {5, 3}  # type: ignore[assignment]
    cmd.HighlightedPointIndex = highlighted  # type: ignore[attr-defined]
    cmd._edit_space_for_translate = lambda: edit_space  # type: ignore[method-assign]
    return cmd


def _rigid_command(controller: _RecordingController, space: Space,
                   view_type: ViewType | None) -> ManipulateRigidTransformCommand:
    """Build the command without the Qt/DI machinery, as tests/test_rigid_drag_cancel does."""
    cmd = object.__new__(ManipulateRigidTransformCommand)
    cmd._transform_controller = controller  # type: ignore[assignment]
    cmd._space = space
    cmd._view_type = lambda: view_type  # type: ignore[method-assign]
    return cmd


class TestArrowKeyNudgeHelper(unittest.TestCase):
    """The shared helper matches the old inline logic for every key and modifier mix."""

    @settings(max_examples=200, deadline=None)
    @given(event=_key_events())
    def test_matches_reference(self, event: QKeyEvent) -> None:
        expected = _reference_nudge_yx(event)
        actual = arrow_key_nudge_yx(event)
        if expected is None:
            self.assertIsNone(actual)
        else:
            self.assertEqual(actual, tuple(expected))

    def test_named_steps(self) -> None:
        shift_ctrl = Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.ControlModifier
        cases = [
            (Qt.Key.Key_Up, Qt.KeyboardModifier.NoModifier, (1, 0)),
            (Qt.Key.Key_Down, Qt.KeyboardModifier.ShiftModifier, (-5, 0)),
            (Qt.Key.Key_Right, Qt.KeyboardModifier.ControlModifier, (0, 25)),
            (Qt.Key.Key_Left, shift_ctrl, (0, -125)),
            (Qt.Key.Key_Left, Qt.KeyboardModifier.AltModifier, (0, -1)),
            (Qt.Key.Key_A, Qt.KeyboardModifier.ShiftModifier, None),
        ]
        for key, modifiers, expected in cases:
            with self.subTest(key=key, modifiers=modifiers):
                self.assertEqual(arrow_key_nudge_yx(QKeyEvent(QEvent.Type.KeyPress, key, modifiers)),
                                 expected)


class TestControlPointCommandNudge(unittest.TestCase):
    """TranslateControlPointCommand passes the nudge to MovePoint as (dx, dy)."""

    @settings(max_examples=200, deadline=None)
    @given(event=_key_events(), edit_space=st.sampled_from((Space.Source, Space.Target)))
    def test_move_point_arguments(self, event: QKeyEvent, edit_space: Space) -> None:
        controller = _RecordingController()
        _control_point_command(controller, edit_space).on_key_down(event)

        expected = _reference_nudge_yx(event)
        if expected is None:
            self.assertEqual(controller.calls, [])
            return
        self.assertEqual(len(controller.calls), 1)
        name, args, kwargs = controller.calls[0]
        self.assertEqual(name, "MovePoint")
        self.assertEqual(sorted(args[0]), [3, 5])
        self.assertEqual((args[1], args[2]), (expected[1], expected[0]))
        self.assertEqual(kwargs, {"space": edit_space})

    def test_no_highlighted_point_does_nothing(self) -> None:
        controller = _RecordingController()
        cmd = _control_point_command(controller, Space.Source, highlighted=None)
        cmd.on_key_down(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Up, Qt.KeyboardModifier.NoModifier))
        self.assertEqual(controller.calls, [])


class TestRigidCommandNudge(unittest.TestCase):
    """ManipulateRigidTransformCommand negates the nudge on Source and calls Translate."""

    @settings(max_examples=200, deadline=None)
    @given(event=_key_events(),
           space=st.sampled_from((Space.Source, Space.Target)),
           view_type=st.sampled_from((ViewType.Source, ViewType.Target, ViewType.Composite, None)),
           transform_type=st.sampled_from((TransformType.RIGID, TransformType.GRID, TransformType.MESH)))
    def test_translate_arguments(self, event: QKeyEvent, space: Space, view_type: ViewType | None,
                                 transform_type: TransformType) -> None:
        controller = _RecordingController(transform_type)
        _rigid_command(controller, space, view_type).on_key_down(event)

        locked = (view_type != ViewType.Composite and space == Space.Target
                  and transform_type in (TransformType.RIGID, TransformType.GRID))
        expected = _reference_nudge_yx(event)
        if locked or expected is None:
            self.assertEqual(controller.calls, [])
            return
        if space == Space.Source:
            expected = [-expected[0], -expected[1]]
        self.assertEqual(controller.calls, [("Translate", (expected,), {"space": space})])


if __name__ == "__main__":
    unittest.main()
