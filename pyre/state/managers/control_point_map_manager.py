from pyre.viewmodels.controlpointmap import ControlPointMap
from pyre.interfaces.managers.control_point_map_manager import IControlPointMapManager, ControlPointManagerKey


class ControlPointMapManager(IControlPointMapManager):
    """Tracks ControlPointMaps for a TransformController and a space to prevent rebuilding data structures constantly"""

    _maps: dict[ControlPointManagerKey, ControlPointMap]

    def __init__(self):
        self._maps = {}

    def getorcreate(self, key: ControlPointManagerKey) -> ControlPointMap:
        """Gets a ControlPointMap if it exists, otherwise creates one"""
        try:
            map = self[key]
            return map
        except KeyError:
            map = ControlPointMap(key.transform_controller, key.space, view_type=key.view_type)
            self[key] = map
            return map

    def __getitem__(self, key: ControlPointManagerKey) -> ControlPointMap:
        """Returns the Control Point Map for the specified TransformController and space"""
        if key not in self._maps:
            raise KeyError(f"No ControlPointMap for key {key}")
        return self._maps[key]

    def __setitem__(self, key: ControlPointManagerKey, value: ControlPointMap):
        """Stores the ControlPointMap for the specified TransformController and space"""
        self._maps[key] = value
