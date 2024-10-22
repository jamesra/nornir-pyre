from __future__ import annotations
from numpy.typing import NDArray
import numpy as np
import abc

import nornir_imageregistration
from nornir_imageregistration import PointLike
from pyre.command_interfaces import ICommand
from pyre.selection_event_data import SelectionEventData


class IRegion(abc.ABC):
    """Interface to an object that can start commands for an interactable region"""

    @property
    @abc.abstractmethod
    def centroid(self) -> NDArray[(2,), np.floating]:
        """The center of the region, may not match bounding box for bounding_box depending on how centroid is calculated"""
        raise NotImplementedError()

    @property
    @abc.abstractmethod
    def bounding_box(self) -> nornir_imageregistration.Rectangle | None:
        """The bounding box of the region, or None for a point"""
        raise NotImplementedError()

    @abc.abstractmethod
    def interaction_distance(self, event: SelectionEventData) -> float | None:
        """
        :return A float indicating distance (weight) to the interactable region.  Lower values are closer.  None is returned if no interaction is possible
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def GetInteractiveCommandForPosition(self, event: SelectionEventData) -> ICommand | None:
        """Return the command to execute for the given position"""
        raise NotImplementedError()


class IRegionMap(abc.ABC):
    """Interface to a class that manages a collection of regions.  Oriented towards search and add/remove operations"""

    @abc.abstractmethod
    def add(self, obj: IRegion) -> int:
        """
        Add an object to the searchable regions
        :return: A unique key for the object, or KeyError if the object is already in the manager
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def tryremove(self, key: int) -> bool:
        """Remove an object from the searchable regions
        :return: True if the object was removed, False if the object was not found
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def clear(self):
        """Remove all objects from the searchable regions"""
        raise NotImplementedError()
