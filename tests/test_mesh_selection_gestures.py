"""Tests for mesh selection gestures and set-operation application."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

import numpy as np
from PyQt6.QtCore import Qt

from pyre.commands.stos.actionmaphelpers import mesh_can_delete, mesh_get_action
from pyre.commands.togglecontrolpointselectioncommand import apply_selection_set_operation
from pyre.interfaces.action import ControlPointAction
from pyre.observable import ObservableSet, SetOperation
from pyre.selection_event_data import InputEvent, InputModifiers, InputSource, SelectionEventData


def _event(
        *,
        input_event: InputEvent,
        modifiers: InputModifiers = InputModifiers.NoModifiers,
        keycode: int | None = None,
        existing: set[int] | None = None,
        position: tuple[float, float] = (0.0, 0.0),
) -> SelectionEventData:
    return SelectionEventData(
        camera=MagicMock(scale=1.0),
        source=InputSource.Keyboard if keycode is not None else InputSource.Mouse,
        input=input_event,
        modifiers=modifiers,
        position=np.array(position, dtype=float),
        keycode=keycode,
        existing_selections=None if existing is None else ObservableSet(existing),
    )


def _always_can_delete(_event: SelectionEventData, _interactions: set[int]) -> bool:
    return True


class TestMeshGetActionSelection(unittest.TestCase):
    """Empty-space click vs drag, shift-toggle, and Delete key."""

    def test_empty_press_is_none(self) -> None:
        event = _event(
            input_event=InputEvent.Press,
            modifiers=InputModifiers.LeftMouseButton,
        )
        result = mesh_get_action(event, set(), _always_can_delete)
        self.assertEqual(result.action, ControlPointAction.NONE)

    def test_empty_drag_no_modifiers_is_box_select(self) -> None:
        event = _event(
            input_event=InputEvent.Drag,
            modifiers=InputModifiers.LeftMouseButton,
        )
        result = mesh_get_action(event, set(), _always_can_delete)
        self.assertEqual(result.action, ControlPointAction.BOX_SELECT)

    def test_empty_shift_drag_is_box_select(self) -> None:
        event = _event(
            input_event=InputEvent.Drag,
            modifiers=InputModifiers.LeftMouseButton | InputModifiers.ShiftKey,
        )
        result = mesh_get_action(event, set(), _always_can_delete)
        self.assertEqual(result.action, ControlPointAction.BOX_SELECT)

    def test_empty_alt_drag_is_lasso_select(self) -> None:
        event = _event(
            input_event=InputEvent.Drag,
            modifiers=InputModifiers.LeftMouseButton | InputModifiers.AltKey,
        )
        result = mesh_get_action(event, set(), _always_can_delete)
        self.assertEqual(result.action, ControlPointAction.LASSO_SELECT)

    def test_empty_release_clears_selection(self) -> None:
        event = _event(
            input_event=InputEvent.Release,
            modifiers=InputModifiers.LeftMouseButtonChanged,
        )
        result = mesh_get_action(event, set(), _always_can_delete)
        self.assertEqual(result.action, ControlPointAction.REPLACE_SELECTION)

    def test_empty_shift_release_creates_point(self) -> None:
        event = _event(
            input_event=InputEvent.Release,
            modifiers=InputModifiers.LeftMouseButtonChanged | InputModifiers.ShiftKey,
        )
        result = mesh_get_action(event, set(), _always_can_delete)
        self.assertEqual(result.action, ControlPointAction.CREATE)

    def test_shift_press_on_point_toggles(self) -> None:
        event = _event(
            input_event=InputEvent.Press,
            modifiers=InputModifiers.LeftMouseButton | InputModifiers.ShiftKey,
        )
        result = mesh_get_action(event, {2}, _always_can_delete)
        self.assertEqual(result.action, ControlPointAction.TOGGLE_SELECTION)

    def test_delete_key_with_selection(self) -> None:
        event = _event(
            input_event=InputEvent.Press,
            keycode=Qt.Key.Key_Delete,
            existing={0, 1},
        )
        result = mesh_get_action(event, set(), lambda e, i: mesh_can_delete(10, e, i))
        self.assertEqual(result.action, ControlPointAction.DELETE)
        self.assertEqual(result.point_indicies, {0, 1})

    def test_backspace_with_selection(self) -> None:
        event = _event(
            input_event=InputEvent.Press,
            keycode=Qt.Key.Key_Backspace,
            existing={3},
        )
        result = mesh_get_action(event, set(), lambda e, i: mesh_can_delete(8, e, i))
        self.assertEqual(result.action, ControlPointAction.DELETE)

    def test_delete_key_blocked_when_too_few_points_remain(self) -> None:
        event = _event(
            input_event=InputEvent.Press,
            keycode=Qt.Key.Key_Delete,
            existing={0, 1},
        )
        result = mesh_get_action(event, set(), lambda e, i: mesh_can_delete(4, e, i))
        self.assertEqual(result.action, ControlPointAction.NONE)

    def test_empty_drag_with_existing_selection_is_box_not_translate(self) -> None:
        event = _event(
            input_event=InputEvent.Drag,
            modifiers=InputModifiers.LeftMouseButton,
            existing={1, 2},
        )
        result = mesh_get_action(event, set(), _always_can_delete)
        self.assertEqual(result.action, ControlPointAction.BOX_SELECT)

    def test_empty_alt_release_with_one_selection_calls_to_mouse(self) -> None:
        event = _event(
            input_event=InputEvent.Release,
            modifiers=InputModifiers.LeftMouseButtonChanged | InputModifiers.AltKey,
            existing={4},
        )
        result = mesh_get_action(event, set(), _always_can_delete)
        self.assertEqual(result.action, ControlPointAction.CALL_TO_MOUSE)
        event = _event(
            input_event=InputEvent.Drag,
            modifiers=InputModifiers.LeftMouseButton | InputModifiers.ControlKey,
        )
        result = mesh_get_action(event, set(), _always_can_delete)
        self.assertEqual(result.action, ControlPointAction.TRANSLATE_ALL)


class TestApplySelectionSetOperation(unittest.TestCase):
    """Replace vs union on ObservableSet without starting a Qt drag."""

    def test_replace_clears_then_adds(self) -> None:
        selected = ObservableSet[int]({1, 2})
        apply_selection_set_operation(selected, {3, 4}, SetOperation.Replace)
        self.assertEqual(selected, {3, 4})

    def test_union_adds_to_existing(self) -> None:
        selected = ObservableSet[int]({1, 2})
        apply_selection_set_operation(selected, {2, 3}, SetOperation.Union)
        self.assertEqual(selected, {1, 2, 3})

    def test_replace_with_empty_clears(self) -> None:
        selected = ObservableSet[int]({1})
        apply_selection_set_operation(selected, set(), SetOperation.Replace)
        self.assertEqual(selected, set())
