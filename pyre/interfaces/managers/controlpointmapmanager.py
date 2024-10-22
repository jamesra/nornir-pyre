from __future__ import annotations

import abc
from typing import NamedTuple
from pyre.space import Space


# from pyre.viewmodels.controlpointmap import ControlPointMap


class ControlPointManagerKey(NamedTuple):
    transform_controller: 'pyre.controllers.transformcontroller.TransformController'
    space: float | Space


class IControlPointMapManager(abc.ABC):
    """Tracks ControlPointMaps for a TransformController and a space to prevent rebuilding data structures constantly"""

    @abc.abstractmethod
    def getorcreate(self, key: ControlPointManagerKey) -> 'pyre.viewmodels.ControlPointMap':
        """Gets a ControlPointMap if it exists, otherwise creates one"""
        raise NotImplementedError

    @abc.abstractmethod
    def __getitem__(self, key: ControlPointManagerKey) -> 'pyre.viewmodels.ControlPointMap':
        """Returns the Control Point Map for the specified TransformController and space"""
        raise NotImplementedError

    @abc.abstractmethod
    def __setitem__(self, key: ControlPointManagerKey, value: dict[Space, 'pyre.viewmodels.ControlPointMap']):
        raise NotImplementedError
