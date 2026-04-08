from dependency_injector.wiring import Provide, inject

from nornir_imageregistration import PointLike
from pyre.selection_event_data import InputModifiers, SelectionEventData, InputEvent
from pyre.settings import AppSettings, UISettings
from pyre.interfaces.managers.command_manager import IActionMap
from pyre.interfaces.action import ControlPointAction, ControlPointActionResult
from pyre.container import IContainer
from pyre.commands.stos.actionmaphelpers import resolve_space_register_action


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

        interactions = set()
        actions = ControlPointAction.NONE
        if event.IsMouseInput | event.IsKeyboardInput:
            if event.IsOnlyShiftPressed:
                actions = ControlPointAction.CREATE
            elif event.IsKeyChordPressed(InputModifiers.AltKey | InputModifiers.ShiftKey):
                actions = ControlPointAction.CREATE_REGISTER
            elif event.IsChordPressed(InputModifiers.ControlKey):
                actions |= ControlPointAction.TRANSLATE_ALL
            else:
                actions = ControlPointAction.NONE

            return ControlPointActionResult(actions, interactions)

        return ControlPointActionResult(ControlPointAction.NONE, interactions)

    def get_action(self, event: SelectionEventData) -> ControlPointActionResult:
        """
        :return: The action that can be taken for the input.  Only one flag should be set.
        """
        interactions = set()
        register_action = resolve_space_register_action(event, interactions)
        if register_action is not None:
            return register_action

        action = ControlPointAction.NONE
        if event.IsMouseInput or event.IsKeyboardInput:
            if event.input == InputEvent.Press:
                if event.IsLeftMousePressed:
                    if event.IsOnlyShiftPressed:
                        action = ControlPointAction.CREATE
                    elif event.IsKeyChordPressed(InputModifiers.AltKey | InputModifiers.ShiftKey):
                        action = ControlPointAction.CREATE_REGISTER
            elif event.input == InputEvent.Drag:
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
