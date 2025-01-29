import enum


class ObservedAction(enum.IntEnum):
    """The actions that can be observed"""
    NONE = 0,
    ADD = 1  # New items appended to end of the list
    INSERT = 2  # New items inserted into the list
    REMOVE = 3  # Items removed from the list
    CLEAR = 4  # List was cleared
    UPDATE = 5  # Items in the list were updated
    MOVE = 6  # Items in the list were moved
