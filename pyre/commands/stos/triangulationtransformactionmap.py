import enum
from pyre.settings import AppSettings, UISettings
from dependency_injector.wiring import Provide, providers, inject
from dependency_injector import containers
from nornir_imageregistration import PointLike
from typing import Callable
from pyre.command_interfaces import ICommand
from pyre.selection_event_data import InputModifiers, SelectionEventData, InputEvent
from pyre.settings import UISettings
from pyre.viewmodels.controlpointmap import ControlPointMap
from pyre.interfaces.managers.command_manager import IControlPointActionMap
from pyre.interfaces.action import ControlPointAction, ControlPointActionResult
from pyre.container import IContainer

import wx  # Need to map this to localized keycodes if another ui library is used


class TriangulationTransformActionMap(IControlPointActionMap):
    """
    Maps inputs to actions based on control points based on a specific type of transform
    """

    config = UISettings

    control_point_map: ControlPointMap

    @property
    def search_radius(self) -> float:
        return self.config.control_point_search_radius

    @inject
    def __init__(self,
                 control_point_map: ControlPointMap,
                 settings: AppSettings = Provide[IContainer.settings]):
        self.config = settings.ui
        self.control_point_map = control_point_map

    def has_potential_interactions(self, world_position: PointLike) -> bool:
        return len(self.find_potential_interactions(world_position, self.search_radius)) > 0

    def find_interactions(self, world_position: PointLike, scale: float) -> set[int]:
        return self.control_point_map.find_nearest_within(world_position, self.search_radius * scale)

    def can_delete(self, event: SelectionEventData, interactions: set[int]) -> bool:
        """Return true if the transform will have enough control points remaining if all selected points are deleted"""
        unique_selections = event.existing_selections | interactions
        num_selected = len(unique_selections)
        return self.control_point_map.points.shape[0] - num_selected >= 3

    def get_possible_actions(self, event: SelectionEventData) -> ControlPointActionResult:
        """
        :return: The set of flags representing actions that may be taken based on the current position and further inputs.
        For example: If hovering over a control point, TRANSLATE and DELETE might be returned as they would be triggered
        by a left click or SHIFT+right click respectively."""
        interactions = self.find_interactions(event.position, (1 / event.camera.scale))

        actions = ControlPointAction.NONE
        # Check for creating a point
        if event.IsMouseInput | event.IsKeyboardInput:
            if len(interactions) == 0:
                if event.IsOnlyShiftPressed:
                    actions = ControlPointAction.CREATE
                elif event.IsOnlyAltPressed and len(event.existing_selections) == 1:
                    actions = ControlPointAction.CALL_TO_MOUSE
                elif event.IsKeyChordPressed(InputModifiers.AltKey | InputModifiers.ShiftKey):
                    actions = ControlPointAction.CREATE_REGISTER
                else:
                    actions = ControlPointAction.NONE

                return ControlPointActionResult(actions, interactions)
            elif len(interactions) >= 1:
                if event.IsLeftMousePressed:
                    if event.IsKeyChordPressed(InputModifiers.ShiftKey | InputModifiers.AltKey):
                        actions |= ControlPointAction.REGISTER
                    else:
                        actions |= ControlPointAction.TRANSLATE
                elif event.IsRightMousePressed:
                    if event.IsOnlyShiftPressed and self.can_delete(event, interactions):
                        actions |= ControlPointAction.DELETE

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

        # Check for creating a point
        if event.IsMouseInput or event.IsKeyboardInput:
            if event.input == InputEvent.Press:
                if len(interactions) == 0:
                    if event.IsLeftMousePressed:
                        if event.IsOnlyAltPressed and len(event.existing_selections) == 1:
                            return ControlPointActionResult(ControlPointAction.CALL_TO_MOUSE, interactions)
                        elif event.IsOnlyShiftPressed:
                            return ControlPointActionResult(ControlPointAction.CREATE, interactions)
                        elif event.IsKeyChordPressed(InputModifiers.AltKey | InputModifiers.ShiftKey):
                            return ControlPointActionResult(ControlPointAction.CREATE_REGISTER, interactions)
                        elif event.NoModifierKeys:
                            return ControlPointActionResult(ControlPointAction.REPLACE_SELECTION, interactions)

                elif len(interactions) >= 1:
                    if event.IsLeftMousePressed:
                        if event.IsKeyChordPressed(InputModifiers.ShiftKey | InputModifiers.AltKey):
                            return ControlPointActionResult(ControlPointAction.REGISTER, interactions)
                        elif event.IsOnlyShiftPressed:
                            return ControlPointActionResult(ControlPointAction.TOGGLE_SELECTION, interactions)
                        elif event.NoModifierKeys:
                            return ControlPointActionResult(ControlPointAction.REPLACE_SELECTION, interactions)
                    elif event.IsRightMousePressed:
                        if event.IsOnlyShiftPressed and self.can_delete(event, interactions):
                            return ControlPointActionResult(ControlPointAction.DELETE, interactions)
                    # Check for translating a point
                    # We only translate when mouse movement occurs, a press can be a selection of a control point
            elif event.input == InputEvent.Drag:
                if len(interactions) > 0:
                    if event.IsLeftMousePressed and event.NoModifierKeys:
                        return ControlPointActionResult(ControlPointAction.TRANSLATE, interactions)
            # elif event.input == InputEvent.Release:
            #     if len(interactions) > 0:
            #         if event.IsLeftMouseChanged:
            #             if event.IsOnlyShiftPressed:
            #                 return ControlPointActionResult(ControlPointAction.TOGGLE_SELECTION, interactions)
            #             elif event.NoModifierKeys:
            #                 return ControlPointActionResult(ControlPointAction.REPLACE_SELECTION, interactions)

        return ControlPointActionResult(ControlPointAction.NONE, interactions)
