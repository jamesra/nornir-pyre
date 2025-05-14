from typing import NamedTuple
from pyre.space import Space
from pyre.controllers.transformcontroller import TransformController
from pyre.viewmodels.controlpointmap import ControlPointMap
from pyre.interfaces.managers.controlpointmapmanager import IControlPointMapManager, ControlPointManagerKey


class ControlPointMapManager(IControlPointMapManager):
    """Tracks ControlPointMaps for a TransformController and a space to prevent rebuilding data structures constantly"""

    _maps: dict[TransformController, dict[Space, ControlPointMap]] = {}

    def __init__(self):
        self._maps = {}

    def getorcreate(self, key: ControlPointManagerKey) -> ControlPointMap:
        """Gets a ControlPointMap if it exists, otherwise creates one"""
        try:
            map = self[key]
            return map
        except KeyError:
            map = ControlPointMap(key.transform_controller, key.space)
            self[key] = map
            return map

    def __getitem__(self, key: ControlPointManagerKey) -> ControlPointMap:
        """Returns the Control Point Map for the specified TransformController and space"""
        if key.transform_controller not in self._maps:
            raise KeyError(f"No ControlPointMaps for TransformController {key.transform_controller}")

        space_maps = self._maps[key.transform_controller]
        if key.space not in space_maps:
            raise KeyError(f"No ControlPointMap for space {key.space} under {key.transform_controller}")

        return space_maps[key.space]

    def __setitem__(self, key: ControlPointManagerKey, value: dict[Space, ControlPointMap]):
        """Stores the ControlPointMap for the specified TransformController and space"""
        if key.transform_controller not in self._maps:
            space_maps = {}
            self._maps[key.transform_controller] = space_maps
        else:
            space_maps = self._maps[key.transform_controller]

        space_maps[key.space] = value
        return
