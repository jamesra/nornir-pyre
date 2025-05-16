import abc

import numpy as np
from numpy._typing import NDArray

import nornir_imageregistration


class IReadOnlyCamera(abc.ABC):
    """Readinly interface to a generic camera"""

    @property
    @abc.abstractmethod
    def x(self) -> float:
        """Position in volume space"""
        raise NotImplementedError()

    @property
    @abc.abstractmethod
    def y(self) -> float:
        """Position in volume space"""
        raise NotImplementedError()

    @property
    @abc.abstractmethod
    def window_size(self) -> tuple[int, int]:
        """Size of the window camera is within"""
        raise NotImplementedError()

    @property
    @abc.abstractmethod
    def visible_world_size(self):
        return self._view_size

    @property
    @abc.abstractmethod
    def visible_world_width(self) -> float:
        """Visible volume width"""
        return float(self._view_size[nornir_imageregistration.iPoint.X])

    @property
    @abc.abstractmethod
    def visible_world_height(self) -> float:
        """Visible volume height"""
        return float(self._view_size[nornir_imageregistration.iPoint.Y])

    @property
    @abc.abstractmethod
    def aspect(self) -> float:
        """aspect ration of the window"""
        raise NotImplementedError()

    @property
    @abc.abstractmethod
    def scale(self) -> float:
        """Scale (zoom) factor of the camera"""
        raise NotImplementedError()

    def AddOnChangeEventListener(self, func):
        raise NotImplementedError()

    @property
    @abc.abstractmethod
    def projection(self) -> NDArray[np.floating]:
        """projection matrix"""
        raise NotImplementedError()

    @property
    @abc.abstractmethod
    def view(self) -> NDArray[np.floating]:
        """View matrix"""
        raise NotImplementedError()

    @property
    @abc.abstractmethod
    def view_proj(self) -> NDArray[np.floating]:
        """View projection matrix"""
        raise NotImplementedError()
