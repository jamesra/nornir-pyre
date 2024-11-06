import enum
from dependency_injector.wiring import Provide, providers, inject
from dependency_injector import containers
from nornir_imageregistration import PointLike
from typing import Callable
from pyre.command_interfaces import ICommand
from pyre.selection_event_data import InputModifiers, SelectionEventData, InputEvent
from pyre.viewmodels.controlpointmap import ControlPointMap
from pyre.interfaces.managers.command_manager import IControlPointActionMap
from pyre.interfaces.action import ControlPointAction, ControlPointActionResult
from pyre.container import IContainer


class GridTransformActionMap(IControlPointActionMap):
    """
    Maps inputs to actions based on control points based on a specific type of transform.
    Grid transforms do not support adding or removing points
    """

    config = Provide[IContainer.config]
    control_point_map: ControlPointMap

    @property
    def search_radius(self) -> float:
        return self.config['control_point_search_radius']

    @inject
    def __init__(self,
                 control_point_map: ControlPointMap):
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
            if len(interactions) == 0:
                actions = ControlPointAction.NONE

            elif event.IsShiftPressed and event.IsAltPressed:
                actions |= ControlPointAction.REGISTER
            elif event.IsShiftPressed:
                actions = ControlPointAction.NONE
            else:
                actions |= ControlPointAction.REGISTER | ControlPointAction.TRANSLATE

            # Check for translating points
            return ControlPointActionResult(actions, interactions)

        return ControlPointActionResult(ControlPointAction.NONE, interactions)

    def get_action(self, event: SelectionEventData) -> ControlPointActionResult:
        """
        :return: The action that can be taken for the input.  Only one flag should be set.
        """
        interactions = self.find_interactions(event.position, 1 / event.camera.scale)

        action = ControlPointAction.NONE
        # Check for creating a point
        if event.IsMouseInput or event.IsKeyboardInput:
            if event.input == InputEvent.Press:
                if len(interactions) == 0:
                    if event.IsLeftMousePressed:
                        action = ControlPointAction.REPLACE_SELECTION
                # Check for deleting a point
                elif len(interactions) == 1:
                    if event.IsShiftPressed and event.IsAltPressed and event.IsLeftMousePressed:
                        action = ControlPointAction.REGISTER
                    elif event.IsShiftPressed and event.IsLeftMousePressed:
                        action = ControlPointAction.TOGGLE_SELECTION
                    # We only translate when mouse movement occurs, a press can be a selection of a control point
            elif event.input == InputEvent.Drag:
                if event.IsLeftMousePressed:
                    action = ControlPointAction.TRANSLATE
                # Check for translating a point
            elif event.input == InputEvent.Release:
                if len(interactions) > 0:
                    if event.IsLeftMouseChanged:
                        action = ControlPointAction.REPLACE_SELECTION

        return ControlPointActionResult(action, interactions)
