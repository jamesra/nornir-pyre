"""Tracks selectable objects in a view

A manager contains objects that listen to input events in a specific region.
The manager will identify the objects with a possible user interaction when an event occurs in their region.
objects report the distance to the input event, and the manager will select the object with the smallest distance.

The manager then walks the responding objects from nearest to furthest and asks if they can start
a new command for the input.  The first object to return a command is selected and the command is executed.
"""

from __future__ import annotations

from typing import NamedTuple

import numpy as np
import rtree

import nornir_imageregistration
from pyre.command_interfaces import ICommand
from pyre.interfaces.managers.region_manager import IRegion, IRegionMap
from pyre.selection_event_data import SelectionEventData
from pyre.interfaces.managers.command_manager import IControlPointActionMap


class InteractionCandidate(NamedTuple):
    distance: float
    region: IRegion


class RegionMap(IRegionMap, IControlPointActionMap):
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

    def clear(self):
        self._index = rtree.index.Index(interleaved=True)
        self.object_to_key = {}
        self.key_to_object = {}

    def has_potential_interactions(self, event: SelectionEventData) -> bool:
        return len(self.find_potential_interactions(event)) > 0

    def find_potential_interactions(self, event: SelectionEventData) -> list[InteractionCandidate]:
        """Determine the list of possible interactions for the event at a world position.
        First checks the bounding box, then invokes interaction_distance on the object"""
        world_position = event.world_position
        bounds = nornir_imageregistration.Rectangle.CreateFromBounds(
            np.array((world_position[0], world_position[1], world_position[0], world_position[1])))
        keys = list(self._index.intersection(bounds.ToTuple()))
        objects = [self.key_to_object[key] for key in keys]
        candidates = []  # type: list[InteractionCandidate]
        for obj in objects:
            distance = obj.interaction_distance(event)
            if distance is not None:
                candidates.append(InteractionCandidate(distance, obj))

        sorted_candidates = sorted(candidates, key=lambda x: x.distance)
        return sorted_candidates

    def try_get_command(self, event: SelectionEventData) -> ICommand | None:
        """Determine the list of possible interactions, and return the first command nearest the interaction point"""
        objects = self.find_potential_interactions(event)

        # objects should be sorted nearest to furthest, the first object to return a command is the result
        for obj in objects:
            command = obj.region.GetInteractiveCommandForPosition(event)
            if command is not None:
                return command

        return None
