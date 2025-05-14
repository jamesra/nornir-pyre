import ctypes

from OpenGL import GL as gl
import numpy as np
from numpy._typing import NDArray

from pyre.gl_engine.helpers import check_for_error
from pyre.gl_engine.interfaces import IBuffer, IIndexBuffer
from pyre.gl_engine.vertexarraylayout import VertexArrayLayout


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
        self._update_buffer_data(value)

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
                 data: NDArray[np.floating] | None = None,
                 usage: int = gl.GL_STATIC_DRAW,
                 capacity: int | None = None):
        self._layout = layout
        self._data = data
        self._usage = usage
        self._capacity = capacity if capacity is not None else \
            data.nbytes if data is not None else 64  # 64 bytes is the minimum buffer size
        self._create_open_gl_objects(data)

    def _create_open_gl_objects(self, data: NDArray[np.floating] | None):
        """Create the buffer object.  This will break any VAO's that use this buffer."""
        check_for_error()
        self._buffer = gl.glGenBuffers(1)
        check_for_error()

        if data is not None:
            self._update_buffer_data(data)

    def _update_buffer_data(self, data: NDArray[np.floating]):
        """Update the buffer data, should allow existing VAO's to continue to work."""
        data = data.flatten()
        data = np.ascontiguousarray(data)
        gl.glBindBuffer(gl.GL_ARRAY_BUFFER, self.buffer)
        check_for_error()

        # buffer data will be zero if the buffer is not initialized
        buffer_size = gl.glGetBufferParameteriv(gl.GL_ARRAY_BUFFER, gl.GL_BUFFER_SIZE)

        # Expand capacity if needed
        if buffer_size == 0 or self._capacity < data.nbytes:
            self._capacity = data.nbytes
            gl.glBufferData(gl.GL_ARRAY_BUFFER, self.capacity, data, self._usage)
            check_for_error()
        else:  # Expansion not needed, replace the existing data
            assert (buffer_size >= self._capacity)
            gl.glBufferSubData(gl.GL_ARRAY_BUFFER, 0, data.nbytes, data)
            check_for_error()

        gl.glBindBuffer(gl.GL_ARRAY_BUFFER, 0)
        check_for_error()

    def __del__(self):
        if self._buffer is not None:
            gl.glDeleteBuffers(1, [self._buffer])
            self._buffer = None


class GLIndexBuffer(IIndexBuffer):
    """Contains a buffer object for use in OpenGL"""

    _buffer: ctypes.c_uint | None = None
    _data: NDArray[np.integer]
    _usage: int  # How the buffer will be used

    _capacity: int | None  # The number of elements the buffer can hold.  This is different than the number of elements in the data array if the buffer is oversized for dynamic use

    @property
    def data(self) -> NDArray[np.integer]:
        """The data in the buffer"""
        return self._data

    @data.setter
    def data(self, value: NDArray[np.integer]):
        self._data = value
        self._update_buffer_data(value)

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

    def __init__(self,
                 data: NDArray[np.integer] | None = None,
                 usage: int = gl.GL_STATIC_DRAW,
                 capacity: int | None = None):
        self._data = data if data is not None else np.array([], dtype=np.uint16)
        self._usage = usage
        self._capacity = capacity if capacity is not None else \
            data.nbytes if data is not None else 64  # 64 bytes is the minimum buffer size
        self._create_open_gl_objects(data)

    def _create_open_gl_objects(self, data: NDArray[np.integer] | None):
        """Create the buffer object.  This will break any VAO's that use this buffer."""
        check_for_error()
        self._buffer = gl.glGenBuffers(1)
        check_for_error()

        if data is not None:
            self._update_buffer_data(data)

    def _update_buffer_data(self, data: NDArray[np.integer]):
        """Update the buffer data, should allow existing VAO's to continue to work."""
        data = data.flatten()
        data = np.ascontiguousarray(data)
        gl.glBindBuffer(gl.GL_ELEMENT_ARRAY_BUFFER, self.buffer)
        check_for_error()

        # buffer data will be zero if the buffer is not initialized
        buffer_size = gl.glGetBufferParameteriv(gl.GL_ELEMENT_ARRAY_BUFFER, gl.GL_BUFFER_SIZE)

        # Expand capacity if needed
        if buffer_size == 0 or self._capacity < data.nbytes:
            self._capacity = data.nbytes
            gl.glBufferData(gl.GL_ELEMENT_ARRAY_BUFFER, self.capacity, data, self._usage)
            check_for_error()
        else:  # Expansion not needed, replace the existing data
            assert (buffer_size >= self._capacity)
            gl.glBufferSubData(gl.GL_ELEMENT_ARRAY_BUFFER, 0, data.nbytes, data)
            check_for_error()

        gl.glBindBuffer(gl.GL_ELEMENT_ARRAY_BUFFER, 0)
        check_for_error()

    def __del__(self):
        if self._buffer is not None:
            gl.glDeleteBuffers(1, [self._buffer])
            self._buffer = None
