from __future__ import annotations

import abc

from nornir_imageregistration import PointLike
from pyre.command_interfaces import ICommand
from pyre.selection_event_data import SelectionEventData
from pyre.interfaces.managers import IRegion
from pyre.interfaces.action import ControlPointActionResult


class IActionMap(abc.ABC):
    """Determines actions for input events"""

    @abc.abstractmethod
    def get_possible_actions(self, event: SelectionEventData) -> ControlPointActionResult:
        """Return the flagged actions that might be taken based on the current position and possible further inputs.
            For example: If hovering over a control point, TRANSLATE and DELETE might be returned as they would be triggered
            by a left click or SHIFT+right click respectively."""

    @abc.abstractmethod
    def get_action(self, event: SelectionEventData) -> ControlPointActionResult:
        """
        :return: The action that can be taken for the input.  Only one flag should be set.
        """
        raise NotImplementedError()


class IControlPointActionMap(IActionMap):
    """Determines actions for input events based on control points"""

    @abc.abstractmethod
    def has_potential_interactions(self, world_position: PointLike) -> bool:
        """
        A fast method to determine if any potential interactions exist for the given world position.  Further more expensive searches may be required to determine the specific interactions or that interactions do not exist.
        :return: True if any potential interactions exist for the given world position.  Further more expensive searches may be required to determine the specific interactions or that interactions do not exist.
        :param world_position: The world position to search for interactions
        :param search_radius: The maximum distance to search for interactions. Zero to search a single point."""
        raise NotImplementedError

    @abc.abstractmethod
    def find_interactions(self, world_position: PointLike) -> set[IRegion]:
        """:return: A list of objects that can interact with the given world position
        :param world_position: The world position to search for interactions
        :param search_radius: The maximum distance to search for interactions. Zero to search a single point."""
        raise NotImplementedError()
