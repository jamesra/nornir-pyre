import ctypes

import OpenGL.GL as gl
import numpy as np
from numpy.typing import NDArray

import pyre.gl_engine.helpers
from pyre.gl_engine.helpers import check_for_error
from pyre.gl_engine.vertexarraylayout import VertexArrayLayout


class ShaderVAO:
    """Creates a Vertex Array Object for a set of control points and indicies
    that are static and will not change during the lifetime of the object"""
    _vertex_buffer: ctypes.c_uint | None
    _index_buffer: ctypes.c_uint | None
    _vao: ctypes.c_uint | None = None
    _num_elements: int = 0

    @property
    def num_elements(self) -> int:
        """Number of indicies in the VAO"""
        return self._num_elements

    def __init__(self,
                 layout: VertexArrayLayout,
                 verticies: NDArray[np.floating],
                 indicies: NDArray[np.uint16]):
        self._num_elements = len(indicies)
        self.create_open_gl_objects(layout, verticies, indicies)

    def create_open_gl_objects(self,
                               vertex_layout: VertexArrayLayout,
                               verticies: NDArray[np.floating],
                               indicies: NDArray[np.uint16]):
        """Create the VAO"""

        try:
            check_for_error()
            self._vao = gl.glGenVertexArrays(1)
            check_for_error()
            gl.glBindVertexArray(self._vao)
            check_for_error()

            # self._vertex_buffer.bind()
            self._vertex_buffer = gl.glGenBuffers(1)
            check_for_error()
            gl.glBindBuffer(gl.GL_ARRAY_BUFFER, self._vertex_buffer)
            check_for_error()

            flat_verts = verticies.flatten()
            gl.glBufferData(gl.GL_ARRAY_BUFFER, flat_verts, gl.GL_STATIC_DRAW)
            check_for_error()

            self._index_buffer = gl.glGenBuffers(1)
            check_for_error()
            gl.glBindBuffer(gl.GL_ELEMENT_ARRAY_BUFFER, self._index_buffer)
            check_for_error()
            gl.glBufferData(gl.GL_ELEMENT_ARRAY_BUFFER, indicies, gl.GL_STATIC_DRAW)
            check_for_error()

            vertex_layout.add_vertex_attributes()

        finally:
            gl.glBindVertexArray(0)
            check_for_error()

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
            gl.glDeleteBuffers(1, [self._vertex_buffer])
            self._vertex_buffer = None
            gl.glDeleteBuffers(1, [self._index_buffer])
            self._index_buffer = None

            self._vao = None
