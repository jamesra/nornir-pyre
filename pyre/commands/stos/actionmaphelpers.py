from __future__ import annotations

from PyQt6.QtCore import Qt

from nornir_imageregistration import PointLike
from pyre.interfaces.action import ControlPointAction, ControlPointActionResult
from pyre.selection_event_data import InputEvent, SelectionEventData
from pyre.viewmodels.controlpointmap import ControlPointMap


def find_control_point_interactions(
    control_point_map: ControlPointMap, world_position: PointLike, search_radius: float, scale: float
) -> set[int]:
    return control_point_map.find_nearest_within(world_position, search_radius * scale)  # type: ignore[arg-type]


def resolve_space_register_action(
    event: SelectionEventData, interactions: set[int]
) -> ControlPointActionResult | None:
    if event.IsKeyboardInput and event.input == InputEvent.Press and event.keycode == Qt.Key.Key_Space:
        action = ControlPointAction.REGISTER_ALL if event.IsShiftPressed else ControlPointAction.REGISTER
        return ControlPointActionResult(action, interactions)

    return None
