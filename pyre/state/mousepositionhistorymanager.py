import abc

from pyre.state import Space
import numpy as np
from numpy.typing import NDArray


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
    def update_position(self, positions: dict[Space, NDArray[np.floating]]):
        raise NotImplementedError


class MousePositionHistoryManager(IMousePositionHistoryManager):
    """Tracks the last mouse/pen input position in different spaces.
    May be extended to cover mouse positions over time later."""
    _last_positions: dict[Space, NDArray[np.floating]]

    def __init__(self):
        self._last_positions = {}

    def get_position(self, space: Space) -> NDArray[np.floating] | None:
        """Get the last mouse position in the specified space"""
        if space in self._last_positions:
            return tuple(self._last_positions[space])  # type: ignore
        else:
            return None

    def update_position(self, positions: dict[Space, NDArray[np.floating]]):
        self._last_positions = positions
