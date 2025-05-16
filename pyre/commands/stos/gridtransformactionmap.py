import enum
from dependency_injector.wiring import Provide, providers, inject
from dependency_injector import containers

from nornir_imageregistration import PointLike
from typing import Callable
from pyre.command_interfaces import ICommand
from pyre.selection_event_data import InputModifiers, SelectionEventData, InputEvent
from pyre.settings import AppSettings, UISettings
from pyre.viewmodels.controlpointmap import ControlPointMap
from pyre.interfaces.managers.command_manager import IControlPointActionMap
from pyre.interfaces.action import ControlPointAction, ControlPointActionResult
from pyre.container import IContainer

import wx


class GridTransformActionMap(IControlPointActionMap):
    """
    Maps inputs to actions based on control points based on a specific type of transform.
    Grid transforms do not support adding or removing points
    """

    # config = Provide[IContainer.config]
    _config: UISettings
    control_point_map: ControlPointMap

    @property
    def search_radius(self) -> float:
        return self._config.control_point_search_radius

    @inject
    def __init__(self,
                 control_point_map: ControlPointMap,
                 config: AppSettings = Provide[IContainer.settings]):
        self._config = config.ui
        self.control_point_map = control_point_map

    def has_potential_interactions(self, world_position: PointLike) -> bool:
        return len(self.find_potential_interactions(world_position, self.search_radius)) > 0

    def find_interactions(self, world_position: PointLike, scale: float) -> set[int]:
        return self.control_point_map.find_nearest_within(world_position, self.search_radius * scale)

    def get_possible_actions(self, event: SelectionEventData) -> ControlPointActionResult:
        """
        :return: The set of flags representing actions that may be taken based on the current position and further inputs.
        For example: If hovering over a control point, TRANSLATE and DELETE might be returned as they would be triggered
        by a left click or SHIFT+right click respectively."""
        interactions = self.find_interactions(event.position, (1 / event.camera.scale))

        actions = ControlPointAction.NONE
        # Check for creating a point
        if event.IsMouseInput | event.IsKeyboardInput:
            if event.IsOnlyCtrlPressed:
                actions |= ControlPointAction.TRANSLATE_ALL

            elif len(interactions) == 0:
                if len(event.existing_selections) == 1:
                    if event.IsOnlyAltPressed:
                        actions = ControlPointAction.CALL_TO_MOUSE
                    else:
                        actions = ControlPointAction.NONE
            elif len(interactions) >= 1:
                if event.IsKeyChordPressed(InputModifiers.ShiftKey | InputModifiers.AltKey):
                    actions |= ControlPointAction.REGISTER
                else:
                    actions |= ControlPointAction.TRANSLATE

            # Check for translating points
            return ControlPointActionResult(actions, interactions)

        return ControlPointActionResult(ControlPointAction.NONE, interactions)

    def get_action(self, event: SelectionEventData) -> ControlPointActionResult:
        """
        :return: The action that can be taken for the input.  Only one flag should be set.
        """
        interactions = self.find_interactions(event.position, 1 / event.camera.scale)

        if event.IsKeyboardInput and event.input == InputEvent.Press:
            if event.keycode == wx.WXK_SPACE:
                # If SHIFT is held down, align everything.  Otherwise align the selected point
                if event.IsShiftPressed:
                    return ControlPointActionResult(ControlPointAction.REGISTER_ALL, interactions)
                else:
                    return ControlPointActionResult(ControlPointAction.REGISTER, interactions)
            elif event.keycode == wx.WXK_DELETE:
                return ControlPointActionResult(ControlPointAction.DELETE, interactions)

        action = ControlPointAction.NONE
        # Check for creating a point
        if event.IsMouseInput or event.IsKeyboardInput:
            if event.input == InputEvent.Press:
                # Check for deleting a point
                if len(interactions) == 0:
                    if event.IsLeftMousePressed:
                        if event.IsOnlyAltPressed and len(event.existing_selections) == 1:
                            action = ControlPointAction.CALL_TO_MOUSE
                        elif event.NoModifierKeys:
                            action = ControlPointAction.REPLACE_SELECTION
                        else:
                            action = ControlPointAction.NONE
                elif len(interactions) == 1:
                    if event.IsLeftMousePressed:
                        if event.IsChordPressed(InputModifiers.ShiftKey | InputModifiers.AltKey):
                            action = ControlPointAction.REGISTER
                        elif event.IsOnlyShiftPressed:
                            action = ControlPointAction.TOGGLE_SELECTION
                        elif event.NoModifierKeys:
                            action = ControlPointAction.REPLACE_SELECTION

            elif event.input == InputEvent.Drag:
                if event.IsChordPressed(InputModifiers.ControlKey | InputModifiers.LeftMouseButton):
                    action = ControlPointAction.TRANSLATE_ALL
                elif len(interactions) > 0:
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
