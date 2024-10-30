import enum


class ObservedAction(enum.IntEnum):
    """The actions that can be observed"""
    NONE = 0,
    ADD = enum.auto()  # New items appended to end of the list
    INSERT = enum.auto()  # New items inserted into the list
    REMOVE = enum.auto()  # Items removed from the list
    CLEAR = enum.auto()  # List was cleared
    UPDATE = enum.auto()  # Items in the list were updated
    MOVE = enum.auto()  # Items in the list were moved
