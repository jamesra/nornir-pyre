from numpy.typing import NDArray
import numpy as np
import OpenGL.GL as gl
from OpenGL.arrays import vbo
import ctypes

from pyre.gl_engine import check_for_error, get_gl_type_size
from pyre.gl_engine.shader_base import BaseShader
from pyre.gl_engine import shaders


class ShaderVAO:
    """Creates a Vertex Array Object for a set of control points and indicies that can be rendered with a specific Shader"""
    _vertex_buffer: ctypes.c_uint | None
    _index_buffer: ctypes.c_uint | None
    _vao: ctypes.c_uint | None = None
    _num_indicies: int = 0

    @property
    def num_elements(self) -> int:
        """Number of indicies in the VAO"""
        return self._num_indicies

    def __init__(self,
                 shader: BaseShader,
                 verticies: NDArray[np.floating],
                 indicies: NDArray[np.uint16]):
        self._num_indicies = len(indicies)
        self.create_open_gl_objects(shader, verticies, indicies)

    def create_open_gl_objects(self,
                               shader: BaseShader,
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
            vert_size = flat_verts.nbytes
            gl.glBufferData(gl.GL_ARRAY_BUFFER, flat_verts, gl.GL_STATIC_DRAW)
            check_for_error()

            self._index_buffer = gl.glGenBuffers(1)
            check_for_error()
            gl.glBindBuffer(gl.GL_ELEMENT_ARRAY_BUFFER, self._index_buffer)
            check_for_error()
            gl.glBufferData(gl.GL_ELEMENT_ARRAY_BUFFER, indicies, gl.GL_STATIC_DRAW)
            check_for_error()

            self.add_vertex_attributes(shader)

        finally:
            gl.glBindVertexArray(0)
            check_for_error()

    def add_vertex_attributes(self, shader: BaseShader):
        """Bind verticies to specific attributes"""

        stride = shader.vertex_layout.stride
        offset = 0
        for attrib in shader.vertex_layout.attributes:
            # gl.glVertexAttribPointer(attrib.location, attrib.num_elements, attrib.type, False, shader.attribute_stride,
            #                          None if attrib.offset == 0 else attrib.offset)
            location = attrib.location()
            gl.glVertexAttribPointer(index=location,
                                     size=attrib.num_elements,
                                     type=attrib.type,
                                     normalized=False,
                                     stride=stride,
                                     pointer=ctypes.c_void_p(offset))
            check_for_error()

            offset += attrib.num_elements * get_gl_type_size(attrib.type)

            gl.glEnableVertexAttribArray(location)
            check_for_error()

    def bind(self):
        """Bind the VAO to the context for rendering"""

        gl.glBindVertexArray(self._vao)
        shaders.check_for_error()

    def unbind(self):
        gl.glBindVertexArray(0)
        shaders.check_for_error()

    def __del__(self):
        if self._vao is not None:
            gl.glDeleteVertexArrays(1, [self._vao])
            self._vao = None
            gl.glDeleteBuffers(1, [self._vertex_buffer])
            self._vertex_buffer = None
            gl.glDeleteBuffers(1, [self._index_buffer])
            self._index_buffer = None

            self._vao = None
