from dependency_injector.wiring import Provide, inject

from nornir_imageregistration import PointLike
from pyre.selection_event_data import InputModifiers, SelectionEventData, InputEvent
from pyre.settings import AppSettings, UISettings
from pyre.viewmodels.controlpointmap import ControlPointMap
from pyre.interfaces.managers.command_manager import IControlPointActionMap
from pyre.interfaces.action import ControlPointAction, ControlPointActionResult
from pyre.container import IContainer
from pyre.commands.stos.actionmaphelpers import (
    find_control_point_interactions,
    resolve_space_register_action,
    drag_translate_interactions,
    mesh_can_delete,
    mesh_get_possible_actions,
    mesh_get_action,
)


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
        """True if deleting the indicated points would leave at least three control points (mesh/triangulation rule)."""
        return mesh_can_delete(self.control_point_map.points.shape[0], event, interactions)

    def get_possible_actions(self, event: SelectionEventData) -> ControlPointActionResult:
        """
        :return: The set of flags representing actions that may be taken based on the current position and further inputs.
        For example: If hovering over a control point, TRANSLATE might be returned for a left click or drag."""
        interactions = self.find_interactions(event.position, (1 / event.camera.scale))
        return mesh_get_possible_actions(event, interactions, self.can_delete)

    def get_action(self, event: SelectionEventData) -> ControlPointActionResult:
        """
        :return: The action that can be taken for the input.  Only one flag should be set.
        """
        interactions = self.find_interactions(event.position, 1 / event.camera.scale)
        interactions = drag_translate_interactions(event, interactions)

        register_action = resolve_space_register_action(event, interactions)
        if register_action is not None:
            return register_action

        return mesh_get_action(event, interactions, self.can_delete)
