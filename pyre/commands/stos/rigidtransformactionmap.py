import enum
from dependency_injector.wiring import Provide, providers, inject
from dependency_injector import containers
from pygame.pypm import Input

from nornir_imageregistration import PointLike
from typing import Callable
from pyre.command_interfaces import ICommand
from pyre.selection_event_data import InputModifiers, SelectionEventData, InputEvent
from pyre.settings import AppSettings, UISettings
from pyre.viewmodels.controlpointmap import ControlPointMap
from pyre.interfaces.managers.command_manager import IControlPointActionMap, IActionMap
from pyre.interfaces.action import ControlPointAction, ControlPointActionResult
from pyre.container import IContainer

import wx


class RigidTransformActionMap(IActionMap):
    """
    Maps inputs to actions based on control points based on a specific type of transform.
    Grid transforms do not support adding or removing points
    """

    # config = Provide[IContainer.config]
    _config: UISettings

    @property
    def search_radius(self) -> float:
        return self._config.control_point_search_radius

    @inject
    def __init__(self,
                 config: AppSettings = Provide[IContainer.settings]):
        self._config = config.ui

    def has_potential_interactions(self, world_position: PointLike) -> bool:
        return True

    def find_interactions(self, world_position: PointLike, scale: float) -> set[int]:
        return set()

    def get_possible_actions(self, event: SelectionEventData) -> ControlPointActionResult:
        """
        :return: The set of flags representing actions that may be taken based on the current position and further inputs.
        For example: If hovering over a control point, TRANSLATE and DELETE might be returned as they would be triggered
        by a left click or SHIFT+right click respectively."""

        actions = ControlPointAction.NONE
        # Check for creating a point
        if event.IsMouseInput | event.IsKeyboardInput:
            if event.IsKeyChordPressed(InputModifiers.ShiftKey | InputModifiers.AltKey):
                actions |= ControlPointAction.REGISTER
            else:
                actions |= ControlPointAction.TRANSLATE

            # Check for translating points
            return ControlPointActionResult(actions, set())

        return ControlPointActionResult(ControlPointAction.NONE, set())

    def get_action(self, event: SelectionEventData) -> ControlPointActionResult:
        """
        :return: The action that can be taken for the input.  Only one flag should be set.
        """
        interactions = set()
        if event.IsKeyboardInput and event.input == InputEvent.Press:
            if event.keycode == wx.WXK_SPACE:
                # If SHIFT is held down, align everything.  Otherwise align the selected point
                if event.IsShiftPressed:
                    # TODO: Stos Brute Registration with all angle rotations
                    return ControlPointActionResult(ControlPointAction.NONE, interactions)
                    # return ControlPointActionResult(ControlPointAction.REGISTER_ALL, interactions)
                else:
                    # TODO: Register with no angle rotation
                    return ControlPointActionResult(ControlPointAction.NONE, interactions)
                    # return ControlPointActionResult(ControlPointAction.REGISTER, interactions)

        action = ControlPointAction.NONE
        # Check for creating a point
        if event.IsMouseInput or event.IsKeyboardInput:
            if event.input == InputEvent.Drag:
                if event.IsLeftMousePressed and event.NoModifierKeys:
                    action = ControlPointAction.TRANSLATE
                # Check for translating a point
            # elif event.input == InputEvent.Release:
            #     if len(interactions) > 0:
            #         if event.IsLeftMouseChanged:
            #             if event.IsOnlyShiftPressed:
            #                 action = ControlPointAction.TOGGLE_SELECTION
            #             elif event.NoModifierKeys:
            #                 action = ControlPointAction.REPLACE_SELECTION

        return ControlPointActionResult(action, interactions)
