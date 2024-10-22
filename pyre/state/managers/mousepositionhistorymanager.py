import numpy as np
from numpy.typing import NDArray

from pyre.interfaces.managers.mousepositionhistorymanager import IMousePositionHistoryManager, \
    MousePositionHistoryChangedCallbackEvent
from pyre.space import Space


class MousePositionHistoryManager(IMousePositionHistoryManager):
    """Tracks the last mouse/pen input position in different spaces.
    May be extended to cover mouse positions over time later."""
    _last_positions: dict[Space, NDArray[np.floating]]
    _mouse_position_update_event_listeners: list[MousePositionHistoryChangedCallbackEvent]

    def __init__(self):
        self._last_positions = {}
        self._mouse_position_update_event_listeners = []

    def get_position(self, space: Space) -> NDArray[np.floating] | None:
        """Get the last mouse position in the specified space"""
        if space in self._last_positions:
            return tuple(self._last_positions[space])  # type: ignore
        else:
            return None

    def update_positions(self, positions: dict[Space, NDArray[np.floating]]):
        """Replace the dictionary of values in one call"""
        self._last_positions = positions
        for k, v in positions.values():
            self.fire_change_event(k, v)

    def __getitem__(self, item: Space) -> NDArray[np.floating]:
        return self._last_positions[item]

    def __setitem__(self, key: Space, value: NDArray[np.floating]):
        self._last_positions[key] = value
        self.fire_change_event(key, value)

    def fire_change_event(self, space: Space, position: NDArray[np.floating]):
        for listener in self._mouse_position_update_event_listeners:
            listener(space, position)

    def add_mouse_position_update_event_listener(self, func: MousePositionHistoryChangedCallbackEvent):
        """Subscribes to an event invoked when the mouse position is updated"""
        self._mouse_position_update_event_listeners.append(func)

    def remove_mouse_position_update_event_listener(self, func: MousePositionHistoryChangedCallbackEvent):
        """Unsubscribe from the mouse position update event"""
        self._mouse_position_update_event_listeners.remove(func)
