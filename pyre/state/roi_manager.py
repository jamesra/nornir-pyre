"""Tracks selectable objects in a view

A manager contains objects that listen to input events in a specific region.
The manager will identify the objects with a possible user interaction when an event occurs in their region.
objects report the distance to the input event, and the manager will select the object with the smallest distance.

The manager then walks the responding objects from nearest to furthest and asks if they can start
a new command for the input.  The first object to return a command is selected and the command is executed.
"""

from __future__ import annotations
import abc
import dataclasses
import rtree
from typing import NamedTuple

import numpy as np
import nornir_imageregistration
from nornir_imageregistration import PointLike

from pyre.commands.interfaces import ICommand, SelectionEventData


class IRegion(abc.ABC):
    """Interface to an object that can start commands for an interactable region"""

    @property
    @abc.abstractmethod
    def bounding_box(self) -> nornir_imageregistration.Rectangle:
        """The bounding box of the region"""
        raise NotImplementedError()

    def HasInteraction(self, event: SelectionEventData) -> float:
        """True if the point is within the region
        :return A float indicating distance to the point if the object feels the point should trigger an interaction.
        """
        raise NotImplementedError()

    def GetInteractiveCommandForPosition(self, event: SelectionEventData) -> ICommand | None:
        """Return the command to execute for the given position"""
        raise NotImplementedError()


class InteractionCandidate(NamedTuple):
    distance: float
    region: IRegion


class IRegionManager(abc.ABC):

    def add(self, obj: IRegion) -> int:
        """
        Add an object to the searchable regions
        :return: A unique key for the object, or KeyError if the object is already in the manager
        """
        raise NotImplementedError()

    def tryremove(self, key: int) -> bool:
        """Remove an object from the searchable regions
        :return: True if the object was removed, False if the object was not found
        """
        raise NotImplementedError()

    def clear(self):
        """Remove all objects from the searchable regions"""
        raise NotImplementedError()

    def find_interactions(self, world_position: PointLike) -> list[IRegion]:
        """:return: A list of objects that can interact with the given world position"""
        raise NotImplementedError()

    def try_get_command(self, event: SelectionEventData) -> ICommand | None:
        """:return: The command to execute for the given position or None if no command exists"""
        raise NotImplementedError()


class RegionManager(IRegionManager):
    """
    Contains a collection of regions that can be interacted with and assists in mapping
    interactions to commands
    """
    _index: rtree.index.Index

    object_to_key: dict[IRegion, int]  # Map a specific object instance to a key
    key_to_object: dict[int, IRegion]  # Map a key to a specific object instance

    def __init__(self):
        self._index = rtree.index.Index(interleaved=True)

    def add(self, obj: IRegion) -> int:
        if obj in self.object_to_key:
            raise KeyError("Object already in manager")

        bounds = obj.bounding_box.ToTuple()
        key = id(obj)
        self.key_to_object[key] = obj
        self._index.insert(key, bounds)
        return key

    def tryremove(self, key: int) -> bool:
        if key in self.key_to_object:
            obj = self.key_to_object[key]
            del self.key_to_object[key]
            del self.object_to_key[obj]
            self._index.delete(key)
            return True
        return False

    def find_interactions(self, event: SelectionEventData) -> list[InteractionCandidate]:
        """Determine the list of possible interactions for the event at a world position.
        First checks the bounding box, then invokes HasInteraction on the object"""
        world_position = event.world_position
        bounds = nornir_imageregistration.Rectangle.CreateFromBounds(
            np.array((world_position[0], world_position[1], world_position[0], world_position[1])))
        keys = list(self._index.intersection(bounds.ToTuple()))
        objects = [self.key_to_object[key] for key in keys]
        candidates = []  # type: list[InteractionCandidate]
        for obj in objects:
            distance = obj.HasInteraction(event)
            if distance is not None:
                candidates.append(InteractionCandidate(distance, obj))

        sorted_candidates = sorted(candidates, key=lambda x: x.distance)
        return sorted_candidates

    def try_get_command(self, event: SelectionEventData) -> ICommand | None:
        """Determine the list of possible interactions, and return the first command nearest the interaction point"""
        objects = self.find_interactions(event)

        # objects should be sorted nearest to furthest, the first object to return a command is the result
        for obj in objects:
            command = obj.region.GetInteractiveCommandForPosition(event)
            if command is not None:
                return command

        return None
