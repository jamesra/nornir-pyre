import enum
from typing import NamedTuple


class Action(enum.IntEnum):
    ADD = 1
    REMOVE = 2


class ControlPointAction(enum.Flag):
    """Possible interactions for control point(s)"""
    NONE = 0
    CREATE = 1  # Create a control point
    CREATE_REGISTER = 1 << 1  # Create a control point and auto-register it
    DELETE = 1 << 2
    TRANSLATE = 1 << 3
    TRANSLATE_ALL = 1 << 4  # Translate all points
    REGISTER = 1 << 5  # Register the selected control points
    REGISTER_ALL = 1 << 6  # Register all points
    SELECT = 1 << 7  # Select the control points under the mouse
    ROTATE = 1 << 8  # Rotate the selected control points
    RECALL = 1 << 9  # Call the selected control points to the mouse cursor
    REPLACE_SELECTION = 1 << 10  # Set the selection to the control points under the mouse
    APPEND_SELECTION = 1 << 11  # Add the control points to the selection
    TOGGLE_SELECTION = 1 << 12  # Toggle the selection of the control points
    CALL_TO_MOUSE = 1 << 13  # Call the selected control point to the mouse cursor


class ControlPointActionResult(NamedTuple):
    action: ControlPointAction
    point_indicies: set[int] | None  # Control points that triggered the action, if any

    def __str__(self):
        return f"{self.action} indicies={self.point_indicies})"

    def __repr__(self):
        return f"{self.action} indicies={self.point_indicies})"
