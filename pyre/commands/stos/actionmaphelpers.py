from __future__ import annotations



from collections.abc import Callable



from PyQt6.QtCore import Qt



from nornir_imageregistration import PointLike

from pyre.interfaces.action import ControlPointAction, ControlPointActionResult

from pyre.selection_event_data import InputEvent, InputModifiers, SelectionEventData

from pyre.viewmodels.controlpointmap import ControlPointMap





def find_control_point_interactions(

    control_point_map: ControlPointMap, world_position: PointLike, search_radius: float, scale: float

) -> set[int]:

    """Return the nearest control point within search_radius world units (scale = 1/camera.scale)."""

    return control_point_map.find_nearest_within(world_position, search_radius * scale)  # type: ignore[arg-type]





def drag_translate_interactions(

        event: SelectionEventData,

        interactions: set[int]) -> set[int]:

    """During drag, keep translating the active selection even if the cursor leaves the pick radius."""

    if event.input != InputEvent.Drag or not event.existing_selections:

        return interactions

    if interactions:

        return interactions

    return set(event.existing_selections)





def resolve_space_register_action(

    event: SelectionEventData, interactions: set[int]

) -> ControlPointActionResult | None:

    if event.IsKeyboardInput and event.input == InputEvent.Press and event.keycode == Qt.Key.Key_Space:

        action = ControlPointAction.REGISTER_ALL if event.IsShiftPressed else ControlPointAction.REGISTER

        return ControlPointActionResult(action, interactions)



    return None





def mesh_can_delete(

        point_count: int,

        event: SelectionEventData,

        interactions: set[int]) -> bool:

    """True when deleting ``interactions`` would leave at least three control points."""

    unique_selections = (event.existing_selections or set()) | interactions

    return point_count - len(unique_selections) >= 3





def mesh_get_possible_actions(

        event: SelectionEventData,

        interactions: set[int],

        can_delete_fn: Callable[[SelectionEventData, set[int]], bool]) -> ControlPointActionResult:

    """Shared hover/preview action resolution for mesh and grid transforms."""

    actions = ControlPointAction.NONE

    if event.IsMouseInput | event.IsKeyboardInput:

        if len(interactions) == 0:

            if event.IsOnlyShiftPressed:

                actions = ControlPointAction.CREATE

            elif event.IsOnlyAltPressed and len(event.existing_selections or set()) == 1:

                actions = ControlPointAction.CALL_TO_MOUSE

            elif event.IsKeyChordPressed(InputModifiers.AltKey | InputModifiers.ShiftKey):

                actions = ControlPointAction.CREATE_REGISTER

            elif event.IsChordPressed(InputModifiers.ControlKey):

                actions |= ControlPointAction.TRANSLATE_ALL

            return ControlPointActionResult(actions, interactions)

        if len(interactions) >= 1:

            if event.IsOnlyShiftPressed and can_delete_fn(event, interactions):

                actions |= ControlPointAction.DELETE

            elif event.IsLeftMousePressed:

                if event.IsKeyChordPressed(InputModifiers.ShiftKey | InputModifiers.AltKey):

                    actions |= ControlPointAction.REGISTER

                elif event.IsOnlyCtrlPressed:

                    actions |= ControlPointAction.TRANSLATE_ALL

                else:

                    actions |= ControlPointAction.TRANSLATE

            elif event.IsRightMousePressed:

                if event.IsOnlyShiftPressed and can_delete_fn(event, interactions):

                    actions |= ControlPointAction.DELETE

        return ControlPointActionResult(actions, interactions)

    return ControlPointActionResult(ControlPointAction.NONE, interactions)





def mesh_get_action(

        event: SelectionEventData,

        interactions: set[int],

        can_delete_fn: Callable[[SelectionEventData, set[int]], bool]) -> ControlPointActionResult:

    """Shared press/drag action resolution for mesh and grid transforms."""

    action = ControlPointAction.NONE

    if event.IsMouseInput or event.IsKeyboardInput:

        if event.input == InputEvent.Press:

            if len(interactions) == 0:

                if event.IsLeftMousePressed:

                    if event.IsOnlyAltPressed and event.existing_selections is not None and len(event.existing_selections) == 1:

                        action = ControlPointAction.CALL_TO_MOUSE

                    elif event.IsOnlyShiftPressed:

                        action = ControlPointAction.CREATE

                    elif event.IsKeyChordPressed(InputModifiers.AltKey | InputModifiers.ShiftKey):

                        action = ControlPointAction.CREATE_REGISTER

                    elif event.NoModifierKeys:

                        action = ControlPointAction.REPLACE_SELECTION

            elif len(interactions) >= 1:

                if event.IsLeftMousePressed:

                    if event.IsKeyChordPressed(InputModifiers.ShiftKey | InputModifiers.AltKey):

                        action = ControlPointAction.REGISTER

                    elif event.IsOnlyShiftPressed:

                        action = ControlPointAction.TOGGLE_SELECTION

                    elif event.NoModifierKeys:

                        action = ControlPointAction.REPLACE_SELECTION

                elif event.IsRightMousePressed:

                    if event.IsOnlyShiftPressed and can_delete_fn(event, interactions):

                        action = ControlPointAction.DELETE

        elif event.input == InputEvent.Drag:

            if event.IsChordPressed(InputModifiers.ControlKey | InputModifiers.LeftMouseButton):

                action = ControlPointAction.TRANSLATE_ALL

            elif len(interactions) > 0:

                if event.IsLeftMousePressed and event.NoModifierKeys:

                    action = ControlPointAction.TRANSLATE

    return ControlPointActionResult(action, interactions)

