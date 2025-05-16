from abc import ABC, abstractmethod
import ctypes

import numpy as np
from numpy.typing import NDArray

from .vertexarraylayout import VertexArrayLayout


class IVAO(ABC):
    """Generic interface for a VAO"""

    @abstractmethod
    def bind(self):
        """Bind the VAO"""
        raise NotImplementedError()

    @abstractmethod
    def unbind(self):
        raise NotImplementedError()


class IIndexBuffer(ABC):
    @property
    @abstractmethod
    def buffer(self) -> ctypes.c_uint:
        """The OpenGL buffer object"""
        raise NotImplementedError()


class IBuffer(ABC):
    """An object with an OpenGL buffer object."""

    @property
    @abstractmethod
    def buffer(self) -> ctypes.c_uint:
        """The OpenGL buffer object"""
        raise NotImplementedError()

    @property
    @abstractmethod
    def layout(self) -> VertexArrayLayout:
        """Layout of the buffer"""
        raise NotImplementedError()


class IFloatInstanceBuffer(IBuffer):
    """An object with an OpenGL buffer object."""

    @property
    @abstractmethod
    def num_instances(self) -> int:
        """The number of instances in the buffer"""
        raise NotImplementedError()

    @property
    @abstractmethod
    def data(self) -> NDArray[np.floating]:
        """The data in the buffer"""
        raise NotImplementedError()
