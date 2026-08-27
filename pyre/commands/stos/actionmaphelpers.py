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
    """Return the nearest control point within the on-screen glyph.

    Glyphs are a ±0.5 quad scaled by ``search_radius * scale`` (``scale`` is
    ``1/camera.scale``), so the visual half-extent is ``0.5 * search_radius * scale``.
    """
    return control_point_map.find_nearest_within(world_position, 0.5 * search_radius * scale)  # type: ignore[arg-type]


def drag_translate_interactions(
        event: SelectionEventData,
        interactions: set[int]) -> set[int]:
    """Keep a point-pick during drag. Empty-space drags start region select instead of translate."""
    if event.input != InputEvent.Drag:
        return interactions
    return interactions


def resolve_space_register_action(
        event: SelectionEventData, interactions: set[int]
) -> ControlPointActionResult | None:
    if event.IsKeyboardInput and event.input == InputEvent.Press and event.keycode == Qt.Key.Key_Space:
        action = ControlPointAction.REGISTER_ALL if event.IsShiftPressed else ControlPointAction.REGISTER
        selected = set(event.existing_selections or ())
        return ControlPointActionResult(action, selected | interactions)
    return None


def resolve_delete_key_action(
        event: SelectionEventData,
        interactions: set[int],
        can_delete_fn: Callable[[SelectionEventData, set[int]], bool],
) -> ControlPointActionResult | None:
    """Delete/Backspace deletes the current selection when the mesh would keep at least three points."""
    if not event.IsKeyboardInput or event.input != InputEvent.Press:
        return None
    if event.keycode not in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
        return None
    if not event.existing_selections:
        return None
    if not can_delete_fn(event, set()):
        return None
    return ControlPointActionResult(ControlPointAction.DELETE, set(event.existing_selections))


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
                if len(event.existing_selections or ()) <= 1:
                    actions |= ControlPointAction.TRANSLATE_ALL
            elif event.IsOnlyAltPressed:
                actions = ControlPointAction.LASSO_SELECT
            else:
                actions = ControlPointAction.BOX_SELECT
            return ControlPointActionResult(actions, interactions)

        if len(interactions) >= 1:
            if event.IsOnlyShiftPressed and can_delete_fn(event, interactions):
                actions |= ControlPointAction.DELETE
            elif event.IsLeftMousePressed:
                if event.IsKeyChordPressed(InputModifiers.ShiftKey | InputModifiers.AltKey):
                    actions |= ControlPointAction.REGISTER
                elif event.IsOnlyCtrlPressed:
                    if len(event.existing_selections or ()) <= 1:
                        actions |= ControlPointAction.TRANSLATE_ALL
                else:
                    actions |= ControlPointAction.TRANSLATE
            elif event.IsRightMousePressed:
                if event.IsOnlyShiftPressed and can_delete_fn(event, interactions):
                    actions |= ControlPointAction.DELETE
        return ControlPointActionResult(actions, interactions)

    return ControlPointActionResult(ControlPointAction.NONE, interactions)


def _empty_click_action(event: SelectionEventData) -> ControlPointAction:
    """Click-without-drag on empty space: clear, create, or call-to-mouse."""
    if event.IsOnlyAltPressed and event.existing_selections is not None and len(event.existing_selections) == 1:
        return ControlPointAction.CALL_TO_MOUSE
    if event.IsOnlyShiftPressed:
        return ControlPointAction.CREATE
    if event.IsKeyChordPressed(InputModifiers.AltKey | InputModifiers.ShiftKey):
        return ControlPointAction.CREATE_REGISTER
    if event.NoModifierKeys:
        return ControlPointAction.REPLACE_SELECTION
    return ControlPointAction.NONE


def _empty_drag_action(event: SelectionEventData) -> ControlPointAction:
    """Left-drag on empty space: box, lasso, or translate-all."""
    if event.IsChordPressed(InputModifiers.ControlKey | InputModifiers.LeftMouseButton):
        if len(event.existing_selections or ()) > 1:
            return ControlPointAction.NONE
        return ControlPointAction.TRANSLATE_ALL
    if not event.IsLeftMousePressed:
        return ControlPointAction.NONE
    if event.IsOnlyAltPressed or event.IsKeyChordPressed(InputModifiers.AltKey | InputModifiers.ShiftKey):
        return ControlPointAction.LASSO_SELECT
    if event.NoModifierKeys or event.IsOnlyShiftPressed:
        return ControlPointAction.BOX_SELECT
    return ControlPointAction.NONE


def mesh_get_action(
        event: SelectionEventData,
        interactions: set[int],
        can_delete_fn: Callable[[SelectionEventData, set[int]], bool]) -> ControlPointActionResult:
    """Shared press/drag/release action resolution for mesh and grid transforms."""
    delete_key = resolve_delete_key_action(event, interactions, can_delete_fn)
    if delete_key is not None:
        return delete_key

    action = ControlPointAction.NONE
    if event.IsMouseInput or event.IsKeyboardInput:
        if event.input == InputEvent.Press:
            if len(interactions) == 0:
                # Empty-space press is delayed so click vs box/lasso can be disambiguated.
                action = ControlPointAction.NONE
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
            if (event.IsChordPressed(InputModifiers.ControlKey | InputModifiers.LeftMouseButton)
                    and len(event.existing_selections or ()) <= 1):
                action = ControlPointAction.TRANSLATE_ALL
            elif len(interactions) == 0:
                action = _empty_drag_action(event)
            elif len(interactions) > 0:
                if event.IsLeftMousePressed and event.IsOnlyShiftPressed:
                    action = ControlPointAction.BOX_SELECT
                elif event.IsLeftMousePressed and event.NoModifierKeys:
                    action = ControlPointAction.TRANSLATE

        elif event.input == InputEvent.Release:
            if len(interactions) == 0 and event.IsLeftMouseChanged:
                action = _empty_click_action(event)

    return ControlPointActionResult(action, interactions)
