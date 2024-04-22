from numpy.typing import NDArray
import numpy as np
import OpenGL.GL as gl
from OpenGL.arrays import vbo

import nornir_imageregistration
from pyre.shader_base import BaseShader
from pyre import shaders


class TextureShaderVAO:
    """Creates a Vertex Array Object for a set of control points and indicies that can be rendered with the Texture Shader"""
    _vertex_buffer: vbo.VBO
    _index_buffer: vbo.VBO
    _vao: int | None = None
    _num_indicies: int = 0

    @property
    def num_elements(self) -> int:
        """Number of indicies in the VAO"""
        return self._num_indicies

    def __init__(self,
                 shader: BaseShader,
                 verticies: NDArray[np.floating],
                 indicies: NDArray[np.uint16]):
        _num_indicies = len(verticies)
        self.create_open_gl_objects(shader, verticies, indicies)

    def create_open_gl_objects(self,
                               shader: BaseShader,
                               verticies: NDArray[np.floating],
                               indicies: NDArray[np.uint16]):
        """Create the VAO"""

        try:

            gl.glUseProgram(shader.program)
            shaders.check_for_error()
            self._vao = gl.glGenVertexArrays(1)
            shaders.check_for_error()
            gl.glBindVertexArray(self._vao)
            shaders.check_for_error()

            # self._vertex_buffer.bind()
            self._vertex_buffer = gl.glGenBuffers(1)
            shaders.check_for_error()
            gl.glBindBuffer(gl.GL_ARRAY_BUFFER, self._vertex_buffer)
            shaders.check_for_error()

            self._specifify_vertex_attribs(shader)
            # stride = verticies.strides[0] * 8
            # stride = 0
            # gl.glVertexAttribPointer(shaders.TextureShader.source_pos_location, 3, gl.GL_FLOAT, False, stride, None)
            # shaders.check_for_error()
            # gl.glVertexAttribPointer(shaders.TextureShader.target_pos_location, 3, gl.GL_FLOAT, False, stride, 3)
            # shaders.check_for_error()
            # gl.glVertexAttribPointer(shaders.TextureShader.texture_location, 2, gl.GL_FLOAT, False, stride, 6)
            # shaders.check_for_error()
            # gl.glEnableVertexAttribArray(shaders.TextureShader.source_pos_location)
            # shaders.check_for_error()
            # gl.glEnableVertexAttribArray(shaders.TextureShader.target_pos_location)
            # shaders.check_for_error()
            # gl.glEnableVertexAttribArray(shaders.TextureShader.texture_location)
            # shaders.check_for_error()

            flat_verts = verticies.flatten()
            vert_size = flat_verts.nbytes
            gl.glBufferData(gl.GL_ARRAY_BUFFER, flat_verts, gl.GL_STATIC_DRAW)
            shaders.check_for_error()

            self._index_buffer = gl.glGenBuffers(1)
            shaders.check_for_error()
            gl.glBindBuffer(gl.GL_ELEMENT_ARRAY_BUFFER, self._index_buffer)
            shaders.check_for_error()
            gl.glBufferData(gl.GL_ELEMENT_ARRAY_BUFFER, indicies.nbytes, indicies, gl.GL_STATIC_DRAW)
            shaders.check_for_error()

        finally:
            shaders.check_for_error()
            gl.glBindBuffer(gl.GL_ARRAY_BUFFER, 0)
            shaders.check_for_error()
            gl.glBindBuffer(gl.GL_ELEMENT_ARRAY_BUFFER, 0)
            shaders.check_for_error()
            gl.glBindVertexArray(0)
            gl.glUseProgram(0)

    def _specifify_vertex_attribs(self, shader: BaseShader):
        """Bind verticies to specific attributes"""
        for attrib in shader.get_attributes():
            gl.glVertexAttribPointer(attrib.location, attrib.num_elements, attrib.type, False, shader.attribute_stride,
                                     None if attrib.offset == 0 else attrib.offset)
            shaders.check_for_error()
            gl.glEnableVertexAttribArray(attrib.location)
            shaders.check_for_error()

    def bind(self):
        """Bind the VAO to the context for rendering"""

        gl.glBindVertexArray(self._vao)
        shaders.check_for_error()

    def unbind(self):
        gl.glBindVertexArray(0)
        shaders.check_for_error()
