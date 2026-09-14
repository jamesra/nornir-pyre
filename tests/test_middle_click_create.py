"""Middle-click creates a control point without holding Shift."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

import numpy as np

from pyre.commands.stos.actionmaphelpers import (
    mesh_get_action,
    middle_click_create_action,
)
from pyre.commands.stos.rigidtransformactionmap import RigidTransformActionMap
from pyre.interfaces.action import ControlPointAction
from pyre.selection_event_data import InputEvent, InputModifiers, InputSource, SelectionEventData
from pyre.settings import AppSettings


def _mouse_event(
        *,
        input_event: InputEvent,
        modifiers: InputModifiers,
        interactions: set[int] | None = None) -> SelectionEventData:
    return SelectionEventData(
        camera=MagicMock(),
        source=InputSource.Mouse,
        input=input_event,
        modifiers=modifiers,
        position=np.array([10.0, 20.0], dtype=float),
        existing_selections=interactions,
    )


class TestMiddleClickCreate(unittest.TestCase):
    def test_middle_press_creates(self) -> None:
        event = _mouse_event(
            input_event=InputEvent.Press,
            modifiers=InputModifiers.MiddleMouseButton,
        )
        result = middle_click_create_action(event)
        assert result is not None
        self.assertEqual(result.action, ControlPointAction.CREATE)

    def test_middle_press_creates_even_over_a_glyph(self) -> None:
        event = _mouse_event(
            input_event=InputEvent.Press,
            modifiers=InputModifiers.MiddleMouseButton,
        )
        result = mesh_get_action(event, {3}, lambda *_: True)
        self.assertEqual(result.action, ControlPointAction.CREATE)

    def test_shift_middle_does_not_create(self) -> None:
        event = _mouse_event(
            input_event=InputEvent.Press,
            modifiers=InputModifiers.MiddleMouseButton | InputModifiers.ShiftKey,
        )
        self.assertIsNone(middle_click_create_action(event))

    def test_middle_release_does_not_create(self) -> None:
        event = _mouse_event(
            input_event=InputEvent.Release,
            modifiers=InputModifiers.MiddleMouseButtonChanged,
        )
        self.assertIsNone(middle_click_create_action(event))

    def test_left_press_empty_space_is_not_create(self) -> None:
        event = _mouse_event(
            input_event=InputEvent.Press,
            modifiers=InputModifiers.LeftMouseButton,
        )
        result = mesh_get_action(event, set(), lambda *_: True)
        self.assertEqual(result.action, ControlPointAction.NONE)

    def test_rigid_middle_press_creates(self) -> None:
        action_map = RigidTransformActionMap(config=AppSettings())
        event = _mouse_event(
            input_event=InputEvent.Press,
            modifiers=InputModifiers.MiddleMouseButton,
        )
        self.assertEqual(action_map.get_action(event).action, ControlPointAction.CREATE)
