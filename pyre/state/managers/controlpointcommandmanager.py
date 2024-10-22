import enum
from dependency_injector.wiring import Provide, providers, inject
from dependency_injector import containers
from nornir_imageregistration import PointLike
from typing import Callable
from pyre.command_interfaces import ICommand
from pyre.selection_event_data import InputModifiers, SelectionEventData, InputEvent
from pyre.viewmodels.controlpointmap import ControlPointMap
from pyre.interfaces.managers.command_manager import IControlPointActionMap
from pyre.interfaces.action import ControlPointAction
from pyre.container import IContainer


class ControlPointActionMap(IControlPointActionMap):
    """
    Contains a collection of control points that can be interacted with
     and assists in mapping input to specific control points
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

    def get_possible_actions(self, event: SelectionEventData) -> ControlPointAction:
        """
        :return: The set of flags representing actions that may be taken based on the current position and further inputs.
        For example: If hovering over a control point, TRANSLATE and DELETE might be returned as they would be triggered
        by a left click or SHIFT+right click respectively."""
        interactions = self.find_interactions(event.position, (1 / event.camera.scale))

        actions = ControlPointAction.NONE
        # Check for creating a point
        if event.IsMouseInput | event.IsKeyboardInput:
            if len(interactions) == 0:
                if event.IsShiftPressed:
                    return ControlPointAction.CREATE
                else:
                    return ControlPointAction.NONE

            elif event.IsShiftPressed and event.IsAltPressed:
                actions |= ControlPointAction.REGISTER
            elif event.IsAltPressed:
                actions |= ControlPointAction.DELETE
            else:
                actions |= ControlPointAction.REGISTER | ControlPointAction.TRANSLATE

            # Check for translating points
            return actions

        return ControlPointAction.NONE

    def get_action(self, event: SelectionEventData) -> ControlPointAction:
        """
        :return: The action that can be taken for the input.  Only one flag should be set.
        """
        interactions = self.find_interactions(event.position, 1 / event.camera.scale)

        # Check for creating a point
        if event.IsMouseInput or event.IsKeyboardInput:
            if len(interactions) == 0:
                if event.IsMouseInput and event.IsLeftMousePressed and event.IsShiftPressed:
                    return ControlPointAction.CREATE

            # Check for deleting a point
            elif len(interactions) == 1:
                if event.IsShiftPressed and event.IsAltPressed and event.IsLeftMousePressed:
                    return ControlPointAction.REGISTER
                if event.IsRightMousePressed and event.IsShiftPressed:
                    return ControlPointAction.DELETE
                # Check for translating a point
                if event.input == InputEvent.Press and event.IsLeftMousePressed:
                    return ControlPointAction.TRANSLATE

        return ControlPointAction.NONE
