import abc
from typing import Any, Callable
import numpy as np
from numpy.typing import NDArray

from pyre.space import Space

# The callback function for the mouse position update event, space is the space the mouse position is in.  The second parameter is the position in that space
MousePositionHistoryChangedCallbackEvent = Callable[[str | Space, NDArray[np.floating]], None]


class IMousePositionHistoryManager(abc.ABC):
    """Tracks the last mouse/pen input position in different spaces.
    May be extended to cover mouse positions over time later."""

    @abc.abstractmethod
    def get_position(self, space: Space) -> tuple[float, float] | None:
        """Get the last mouse position in the specified space
        :param space: The space to get the mouse position in
        :return: The last mouse position in the space or None if the space is not found
        """
        raise NotImplementedError

    @abc.abstractmethod
    def update_positions(self, positions: dict[Space, NDArray[np.floating]]):
        raise NotImplementedError

    @abc.abstractmethod
    def __getitem__(self, item: Space) -> NDArray[np.floating]:
        raise NotImplementedError

    @abc.abstractmethod
    def __setitem__(self, key: Space, value: NDArray[np.floating]):
        raise NotImplementedError

    @abc.abstractmethod
    def add_mouse_position_update_event_listener(self, func: MousePositionHistoryChangedCallbackEvent):
        """Subscribes to an event invoked when the mouse position is updated"""
        raise NotImplementedError()

    @abc.abstractmethod
    def remove_mouse_position_update_event_listener(self, func: MousePositionHistoryChangedCallbackEvent):
        """Unsubscribe from the mouse position update event"""
        raise NotImplementedError()
