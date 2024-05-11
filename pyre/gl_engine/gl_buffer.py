import ctypes

from OpenGL import GL as gl
import numpy as np
from numpy._typing import NDArray

from pyre.gl_engine import VertexArrayLayout, check_for_error
from pyre.gl_engine.interfaces import IBuffer


class GLBuffer(IBuffer):
    """Contains a buffer object for use in OpenGL"""
    _buffer: ctypes.c_uint | None = None
    _layout: VertexArrayLayout
    _data: NDArray[np.floating]
    _usage: int  # How the buffer will be used

    _capacity: int | None  # The number of elements the buffer can hold.  This is different than the number of elements in the data array if the buffer is oversized for dynamic use

    @property
    def data(self) -> NDArray[np.floating]:
        """The data in the buffer"""
        return self._data

    @data.setter
    def data(self, value: NDArray[np.floating]):
        self._data = value

        # Expand capacity if needed
        if self._capacity < self._data.nbytes:
            self._capacity = self._data.nbytes

        # TODO: Update the buffer data because we cannot replace the buffer
        # without breaking the VAO
        self._create_open_gl_objects(value)

    @property
    def buffer(self) -> ctypes.c_uint:
        """The OpenGL buffer object"""
        return self._buffer

    @property
    def usage(self) -> int:
        """
        How the buffer will be used:
        GL_STREAM_DRAW, GL_STREAM_READ, GL_STREAM_COPY, GL_STATIC_DRAW, GL_STATIC_READ, GL_STATIC_COPY,
        GL_DYNAMIC_DRAW, GL_DYNAMIC_READ, or GL_DYNAMIC_COPY.
        """
        return self._usage

    @property
    def capacity(self) -> int:
        """The number of elements the buffer can hold"""
        return self._capacity

    @property
    def layout(self) -> VertexArrayLayout | None:
        """Layout of the buffer, an index buffer does not have an array layout"""
        return self._layout

    def __init__(self,
                 layout: VertexArrayLayout | None,
                 data: NDArray[np.floating],
                 usage: int = gl.GL_STATIC_DRAW,
                 capacity: int | None = None):
        self._layout = layout
        self._data = data
        self._usage = usage
        self._capacity = capacity if capacity is not None else data.nbytes
        self._create_open_gl_objects(data)

    def _create_open_gl_objects(self, data: NDArray[np.floating]):
        """Create the buffer object.  This will break any VAO's that use this buffer."""
        check_for_error()
        self._buffer = gl.glGenBuffers(1)
        check_for_error()

        self._update_buffer_data(data)

    def _update_buffer_data(self, data: NDArray[np.floating]):
        """Update the buffer data, should allow existing VAO's to continue to work."""
        gl.glBindBuffer(gl.GL_ARRAY_BUFFER, self.buffer)
        check_for_error()
        gl.glBufferData(gl.GL_ARRAY_BUFFER, self.capacity, data.flatten(), self._usage)
        check_for_error()
        gl.glBindBuffer(gl.GL_ARRAY_BUFFER, 0)
        check_for_error()

    def __del__(self):
        if self._buffer is not None:
            gl.glDeleteBuffers(1, [self._buffer])
            self._buffer = None
