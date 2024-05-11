import ctypes

from OpenGL import GL as gl
import numpy as np
from numpy._typing import NDArray

import pyre.gl_engine
from pyre.gl_engine import check_for_error
from pyre.gl_engine.interfaces import IBuffer


class InstancedVAO:
    """Defines a Vertex Array Object for a set of buffers with known layouts"""
    _buffers: set[IBuffer]
    _indicies: NDArray[np.uint16] | None = None
    _vao: ctypes.c_uint | None = None
    _num_elements: int = 0
    _intializing: bool = False
    _initialized: bool = False
    _index_buffer: ctypes.c_uint | None = None  # The index buffer

    @property
    def num_elements(self) -> int:
        """Number of indicies in the VAO"""
        return len(self._indicies)

    def __init__(self):
        pass

    def begin_init(self):
        """This is called once, before adding any buffers"""
        if self._initialized:
            raise ValueError("VAO already initialized")
        if self._intializing:
            raise ValueError("VAO already initializing")

        self._intializing = True

        self._buffers = set()
        self._vao = gl.glGenVertexArrays(1)
        gl.glBindVertexArray(self._vao)

    def end_init(self):
        """This is called once, after adding all buffers"""
        if not self._intializing:
            raise ValueError("VAO not initializing")
        if self._initialized:
            raise ValueError("VAO already initialized")
        if not self._index_buffer:
            raise ValueError("Index buffer not added to VAO")
        if len(self._buffers) == 0:
            raise ValueError("No buffers added to VAO")

        self._intializing = False
        self._initialized = True

        gl.glBindVertexArray(0)

    def add_index_buffer(self, indicies: NDArray[np.uint16]):
        if not self._intializing:
            raise ValueError("VAO not initializing")
        if self._initialized:
            raise ValueError("VAO already initialized")

        self._indicies = indicies
        self._index_buffer = gl.glGenBuffers(1)
        check_for_error()
        gl.glBindBuffer(gl.GL_ELEMENT_ARRAY_BUFFER, self._index_buffer)
        check_for_error()
        gl.glBufferData(gl.GL_ELEMENT_ARRAY_BUFFER, indicies, gl.GL_STATIC_DRAW)
        check_for_error()

    def add_buffer(self, buffer: IBuffer):
        """
        Add either a vertex buffer or an instance buffer to the VAO
        :param buffer:
        :return:
        """
        if not self._intializing:
            raise ValueError("VAO not initializing")
        if self._initialized:
            raise ValueError("VAO already initialized")

        if buffer in self._buffers:
            raise ValueError("Buffer already added to VAO")

        self._buffers.add(buffer)
        gl.glBindBuffer(gl.GL_ARRAY_BUFFER, buffer.buffer)
        buffer.layout.add_vertex_attributes()
        gl.glBindBuffer(gl.GL_ARRAY_BUFFER, 0)

    def bind(self):
        """Bind the VAO to the context for rendering"""
        gl.glBindVertexArray(self._vao)
        pyre.gl_engine.helpers.check_for_error()

    def unbind(self):
        gl.glBindVertexArray(0)
        pyre.gl_engine.helpers.check_for_error()

    def __del__(self):
        if self._vao is not None:
            gl.glDeleteVertexArrays(1, [self._vao])
            self._vao = None

        if self._index_buffer is not None:
            gl.glDeleteBuffers(1, [self._index_buffer])
            self._index_buffer = None
