from dependency_injector.wiring import Provide, inject

from nornir_imageregistration import PointLike
from pyre.selection_event_data import InputModifiers, SelectionEventData, InputEvent
from pyre.settings import AppSettings, UISettings
from pyre.viewmodels.controlpointmap import ControlPointMap
from pyre.interfaces.managers.command_manager import IControlPointActionMap
from pyre.interfaces.action import ControlPointAction, ControlPointActionResult
from pyre.container import IContainer
from pyre.commands.stos.actionmaphelpers import find_control_point_interactions, resolve_space_register_action


class GridTransformActionMap(IControlPointActionMap):
    """
    Maps inputs to actions based on control points based on a specific type of transform.
    Grid transforms do not support adding or removing control points in the UI.
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
        return bool(self.find_interactions(world_position, 1.0))

    def find_interactions(self, world_position: PointLike, scale: float) -> set[int]:
        return find_control_point_interactions(self.control_point_map, world_position, self.search_radius, scale)

    def can_delete(self, event: SelectionEventData, interactions: set[int]) -> bool:
        """Grid refinement transforms do not support deleting control points in Pyre."""
        return False

    def get_possible_actions(self, event: SelectionEventData) -> ControlPointActionResult:
        """
        :return: The set of flags representing actions that may be taken based on the current position and further inputs.
        For example: If hovering over a control point, TRANSLATE might be returned for a left click or drag."""
        interactions = self.find_interactions(event.position, (1 / event.camera.scale))

        actions = ControlPointAction.NONE
        # Check for creating a point
        if event.IsMouseInput | event.IsKeyboardInput:
            if event.IsOnlyCtrlPressed:
                actions |= ControlPointAction.TRANSLATE_ALL

            elif len(interactions) == 0:
                if event.existing_selections is not None and len(event.existing_selections) == 1:
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

        register_action = resolve_space_register_action(event, interactions)
        if register_action is not None:
            return register_action

        action = ControlPointAction.NONE
        # Check for creating a point
        if event.IsMouseInput or event.IsKeyboardInput:
            if event.input == InputEvent.Press:
                if len(interactions) == 0:
                    if event.IsLeftMousePressed:
                        if event.IsOnlyAltPressed and event.existing_selections is not None and len(event.existing_selections) == 1:
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
