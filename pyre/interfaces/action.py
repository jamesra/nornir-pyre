import enum
from typing import NamedTuple


class Action(enum.IntEnum):
    ADD = 1
    REMOVE = 2


class ControlPointAction(enum.Flag):
    """Possible interactions for control point(s)"""
    NONE = 0
    CREATE = 1
    DELETE = 2
    TRANSLATE = 4
    REGISTER = 8
    SELECT = 16  # Select the control points under the mouse
    ROTATE = 32  # Rotate the selected control points
    RECALL = 64  # Call the selected control points to the mouse cursor
    REPLACE_SELECTION = 128  # Set the selection to the control points under the mouse
    APPEND_SELECTION = 256  # Add the control points to the selection
    TOGGLE_SELECTION = 512  # Toggle the selection of the control points


class ControlPointActionResult(NamedTuple):
    action: ControlPointAction
    point_indicies: set[int] | None  # Control points that triggered the action, if any

    def __str__(self):
        return f"{self.action} indicies={self.point_indicies})"

    def __repr__(self):
        return f"{self.action} indicies={self.point_indicies})"
