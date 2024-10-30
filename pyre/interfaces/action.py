import enum


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
