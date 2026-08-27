"""Tests for mesh selection gestures and set-operation application."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

import numpy as np
from PyQt6.QtCore import Qt

from hypothesis import example, given, settings
from hypothesis import strategies as st

from pyre.commands.stos.actionmaphelpers import mesh_can_delete, mesh_get_action, mesh_get_possible_actions
from pyre.commands.togglecontrolpointselectioncommand import (
    apply_selection_set_operation,
    apply_shift_region_selection,
)
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

    def test_ctrl_drag_empty_with_no_selection_is_translate_all(self) -> None:
        event = _event(
            input_event=InputEvent.Drag,
            modifiers=InputModifiers.LeftMouseButton | InputModifiers.ControlKey,
        )
        result = mesh_get_action(event, set(), _always_can_delete)
        self.assertEqual(result.action, ControlPointAction.TRANSLATE_ALL)

    def test_ctrl_drag_empty_with_multi_selection_is_not_translate_all(self) -> None:
        event = _event(
            input_event=InputEvent.Drag,
            modifiers=InputModifiers.LeftMouseButton | InputModifiers.ControlKey,
            existing={1, 2},
        )
        result = mesh_get_action(event, set(), _always_can_delete)
        self.assertNotEqual(result.action, ControlPointAction.TRANSLATE_ALL)

    def test_ctrl_drag_empty_with_one_selection_is_translate_all(self) -> None:
        event = _event(
            input_event=InputEvent.Drag,
            modifiers=InputModifiers.LeftMouseButton | InputModifiers.ControlKey,
            existing={1},
        )
        result = mesh_get_action(event, set(), _always_can_delete)
        self.assertEqual(result.action, ControlPointAction.TRANSLATE_ALL)

    def test_shift_drag_on_point_is_box_select(self) -> None:
        event = _event(
            input_event=InputEvent.Drag,
            modifiers=InputModifiers.LeftMouseButton | InputModifiers.ShiftKey,
        )
        result = mesh_get_action(event, {2}, _always_can_delete)
        self.assertEqual(result.action, ControlPointAction.BOX_SELECT)

    def test_ctrl_hover_empty_with_multi_selection_is_not_translate_all(self) -> None:
        event = _event(
            input_event=InputEvent.Drag,
            modifiers=InputModifiers.ControlKey,
            existing={1, 2},
        )
        result = mesh_get_possible_actions(event, set(), _always_can_delete)
        self.assertNotEqual(result.action, ControlPointAction.TRANSLATE_ALL)

    def test_ctrl_hover_empty_with_no_selection_is_translate_all(self) -> None:
        event = _event(
            input_event=InputEvent.Drag,
            modifiers=InputModifiers.ControlKey,
        )
        result = mesh_get_possible_actions(event, set(), _always_can_delete)
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

    def test_shift_click_toggles_single_index(self) -> None:
        selected = ObservableSet[int]({1, 2})
        apply_selection_set_operation(selected, {2}, SetOperation.SymmetricDifference)
        self.assertEqual(selected, {1})
        apply_selection_set_operation(selected, {3}, SetOperation.SymmetricDifference)
        self.assertEqual(selected, {1, 3})

    def test_shift_region_adds_when_selection_empty(self) -> None:
        selected = ObservableSet[int]()
        apply_shift_region_selection(selected, {3, 4})
        self.assertEqual(selected, {3, 4})

    def test_shift_region_adds_when_none_of_hits_selected(self) -> None:
        selected = ObservableSet[int]({1, 2})
        apply_shift_region_selection(selected, {3, 4})
        self.assertEqual(selected, {1, 2, 3, 4})

    def test_shift_region_adds_when_mixed(self) -> None:
        selected = ObservableSet[int]({1, 2})
        apply_shift_region_selection(selected, {2, 3})
        self.assertEqual(selected, {1, 2, 3})

    def test_shift_region_removes_when_all_hits_selected(self) -> None:
        selected = ObservableSet[int]({1, 2, 3})
        apply_shift_region_selection(selected, {2, 3})
        self.assertEqual(selected, {1})

    def test_shift_region_empty_hits_is_noop(self) -> None:
        selected = ObservableSet[int]({1, 2})
        apply_shift_region_selection(selected, set())
        self.assertEqual(selected, {1, 2})

    def test_add_or_remove_group_operation(self) -> None:
        selected = ObservableSet[int]({1, 2, 3})
        apply_selection_set_operation(selected, {2, 3}, SetOperation.AddOrRemoveGroup)
        self.assertEqual(selected, {1})

    def test_difference_update_removes_without_recursing(self) -> None:
        selected = ObservableSet[int]({1, 2, 3})
        selected.difference_update({2, 4})
        self.assertEqual(selected, {1, 3})

    @given(
        selected=st.sets(st.integers(0, 20), max_size=12),
        hits=st.sets(st.integers(0, 20), max_size=12),
    )
    @example(selected=set(), hits={1, 2})
    @example(selected={1, 2, 3}, hits={4, 5})
    @example(selected={1, 2, 3}, hits={2, 3})
    @example(selected={1, 2, 3}, hits={2, 3, 4})
    @example(selected={1, 2}, hits=set())
    @settings(max_examples=80, deadline=None)
    def test_shift_region_property(self, selected: set[int], hits: set[int]) -> None:
        current = ObservableSet[int](selected)
        apply_shift_region_selection(current, hits)
        if not hits:
            self.assertEqual(current, selected)
        elif hits <= selected:
            self.assertEqual(current, selected - hits)
        else:
            self.assertEqual(current, selected | hits)
