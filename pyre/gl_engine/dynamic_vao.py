from numpy.typing import NDArray
import numpy as np
import OpenGL.GL as gl
import ctypes

import pyre.gl_engine.helpers
from pyre.gl_engine.helpers import check_for_error
from pyre.gl_engine.interfaces import IBuffer
from pyre.gl_engine.gl_buffer import GLBuffer, GLIndexBuffer
from pyre.gl_engine.interfaces import IVAO


class DynamicVAO(IVAO):
    """Creates a Vertex Array Object for a set of vertex data that can be updated dynamically"""
    """Defines a Vertex Array Object for a set of buffers with known layouts"""
    _vao: ctypes.c_uint | None = None
    _intializing: bool = False
    _initialized: bool = False
    _index_buffer: GLIndexBuffer = None  # The index buffer
    _buffers: set[IBuffer] = set()  # The vertex buffers

    @property
    def num_elements(self) -> int:
        """Number of indicies in the VAO"""
        return len(self.indicies)

    @property
    def indicies(self) -> NDArray[np.integer]:
        return self._index_buffer.data

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

        valid = gl.glIsVertexArray(self._vao)
        if not valid:
            raise ValueError("VAO is not valid")

    def add_index_buffer(self, value: GLIndexBuffer):
        """Adds the index buffer to the VAO"""
        if not self._intializing:
            raise ValueError("VAO not initializing")
        if self._initialized:
            raise ValueError("VAO already initialized")

        self._index_buffer = value
        check_for_error()
        gl.glBindBuffer(gl.GL_ELEMENT_ARRAY_BUFFER, self._index_buffer.buffer)
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
        check_for_error()

        buffer.layout.add_vertex_attributes()

    def bind(self):
        """Bind the VAO to the context for rendering"""
        valid = gl.glIsVertexArray(self._vao)
        assert (valid != 0)
        gl.glBindVertexArray(self._vao)
        pyre.gl_engine.helpers.check_for_error()

    def unbind(self):
        gl.glBindVertexArray(0)
        pyre.gl_engine.helpers.check_for_error()

    def __del__(self):
        if self._vao is not None:
            gl.glDeleteVertexArrays(1, [self._vao])
            self._vao = None
