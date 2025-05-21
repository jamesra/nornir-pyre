"""
OpenGL interface definitions for the Pyre rendering engine.

This module defines abstract base classes that serve as interfaces for various
OpenGL components used in the rendering pipeline. These interfaces ensure
consistent behavior across different implementations and provide a clear
contract for classes that implement them.

Interfaces:
    IVAO: Interface for Vertex Array Objects
    IIndexBuffer: Interface for index buffers
    IBuffer: Interface for generic buffers
    IFloatInstanceBuffer: Interface for float instance buffers
"""

from abc import ABC, abstractmethod
import ctypes

import numpy as np
from numpy.typing import NDArray

from .vertexarraylayout import VertexArrayLayout


class IVAO(ABC):
    """
    Interface for Vertex Array Objects (VAO).

    A VAO is an OpenGL object that stores all of the state needed to supply
    vertex data to the rendering pipeline. This interface defines the minimum
    methods that any VAO implementation must provide.

    Implementations of this interface are responsible for managing the lifecycle
    of the VAO, including creation, binding, and deletion.
    """

    @abstractmethod
    def bind(self):
        """
        Bind the VAO to the current OpenGL context.

        This makes the VAO active for subsequent rendering operations.
        Only one VAO can be bound at a time.

        Returns:
            None
        """
        raise NotImplementedError()

    @abstractmethod
    def unbind(self):
        """
        Unbind the VAO from the current OpenGL context.

        This deactivates the VAO for subsequent rendering operations.

        Returns:
            None
        """
        raise NotImplementedError()


class IIndexBuffer(ABC):
    """
    Interface for OpenGL index buffers.

    An index buffer contains indices that reference vertices in a vertex buffer.
    This allows for efficient rendering of geometry by reusing vertices.

    Implementations of this interface are responsible for managing the lifecycle
    of the index buffer, including creation, binding, and deletion.
    """

    @property
    @abstractmethod
    def buffer(self) -> int:
        """
        Get the OpenGL buffer object identifier.

        Returns:
            int: The OpenGL buffer object ID that can be used with OpenGL functions
        """
        raise NotImplementedError()


class IBuffer(ABC):
    """
    Interface for OpenGL buffer objects.

    A buffer object is a memory buffer in the OpenGL server's memory that stores
    vertex data, such as vertex coordinates, texture coordinates, normals, etc.

    This interface defines the minimum properties that any buffer implementation
    must provide, including access to the buffer ID and its layout.

    Implementations of this interface are responsible for managing the lifecycle
    of the buffer, including creation, binding, data transfer, and deletion.
    """

    @property
    @abstractmethod
    def buffer(self) -> int:
        """
        Get the OpenGL buffer object identifier.

        Returns:
            int: The OpenGL buffer object ID that can be used with OpenGL functions
        """
        raise NotImplementedError()

    @property
    @abstractmethod
    def layout(self) -> VertexArrayLayout:
        """
        Get the layout of the buffer.

        The layout describes how the data in the buffer is organized, including
        the size, type, and offset of each attribute.

        Returns:
            VertexArrayLayout: The layout of the buffer
        """
        raise NotImplementedError()


class IFloatInstanceBuffer(IBuffer):
    """
    Interface for OpenGL instance buffer objects containing floating-point data.

    An instance buffer is a specialized buffer that contains per-instance data
    for instanced rendering. This interface extends IBuffer with properties
    specific to instance buffers containing floating-point values.

    Instanced rendering allows drawing multiple instances of the same geometry
    with different attributes (like position, color, scale) in a single draw call,
    which is more efficient than drawing each instance separately.

    Implementations of this interface are responsible for managing the lifecycle
    of the instance buffer and providing access to its data and instance count.
    """

    @property
    @abstractmethod
    def num_instances(self) -> int:
        """
        Get the number of instances in the buffer.

        Returns:
            int: The number of instances that can be rendered using this buffer
        """
        raise NotImplementedError()

    @property
    @abstractmethod
    def data(self) -> NDArray[np.floating]:
        """
        Get the floating-point data stored in the buffer.

        Returns:
            NDArray[np.floating]: A NumPy array containing the buffer data
        """
        raise NotImplementedError()
