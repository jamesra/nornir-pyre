__all__ = ['vertex_shader', 'fragment_shader']

import OpenGL.GL as gl
import OpenGL.GL.shaders as glshaders

import math
import time

import numpy as np
from numpy.typing import NDArray

from pyre.shader_base import BaseShader, FragmentShader, VertexAttribute, VertexShader
from pyre.texture_vertex_buffer import TextureShaderVAO

from typing import Sequence


def check_for_error():
    error = gl.glGetError()
    if error != gl.GL_NO_ERROR:
        raise ValueError(f"OpenGL error: {error}")


_texture_const = """ 
        varying vec2 vertex_texture_coordinate_var;
"""

_texture_vertex_shader_program = """
        #version 330
        uniform float tween; //The fractional amount of the tween between source and target space
        uniform mat4 model_view_projection_matrix;
        out vec2 texture_coordinate;
        in vec3 vertex_source_position;
        in vec3 vertex_target_position;
        in vec2 vertex_texture_coordinate;
        void main(){
            gl_Position = model_view_projection_matrix * mix(vec4(vertex_source_position, 1),
                                                             vec4(vertex_target_position, 1),
                                                             tween);
            texture_coordinate = vertex_texture_coordinate;  
        }
"""

_texture_fragment_shader_program = """
    #version 330
    uniform sampler2D texture;
    in vec2 texture_coordinate;
    out vec4 outputColor;
    void main() {
        vec4 texDiffuse = texture2D(
                texture, texture_coordinate
            ); 
        outputColor = mix(texDiffuse, vec4(0.0f, 1.0f, 0.0f, 0.5f), 0.5);
    }
"""

_color_vertex_shader_program = """
        #version 330
        uniform float tween; //The fractional amount of the tween between source and target space
        uniform mat4 model_view_projection_matrix; 
        in vec3 vertex_source_position;
        in vec3 vertex_target_position;
        in vec2 vertex_texture_coordinate;
        void main(){
            gl_Position = model_view_projection_matrix * mix(vec4(vertex_source_position, 1),
                                                             vec4(vertex_target_position, 1),
                                                             tween);
        }
"""

_color_fragment_shader_program = """
    #version 330  
    out vec4 outputColor;
    void main() {
        outputColor = vec4(0.5f, 1.0f, 0.0f, 0.5f);
    }
"""


# _texture_vertex_shader = VertexShader(_texture_vertex_shader_program)
# _texture_fragment_shader = FragmentShader(_texture_fragment_shader_program)


class ColorShader(BaseShader):
    """
    Colors fragments with a constant color, used for testing
    """

    _source_pos_location = None
    _target_pos_location = None
    _tween_location = None
    _model_view_projection_matrix_location = None

    @classmethod
    def get_attributes(cls) -> Sequence[VertexAttribute]:
        return (
            VertexAttribute(cls.source_pos_location, "vertex_source_position", 3, gl.GL_FLOAT, 4, 0),
            VertexAttribute(cls.target_pos_location, "vertex_target_position", 3, gl.GL_FLOAT, 4, 3),
        )

    @classmethod
    def initialize(cls):
        """initialize the static class.  This must be called AFTER the OpenGL context is created."""
        global _color_vertex_shader_program
        global _color_fragment_shader_program

        if cls._vertex_shader is None:
            cls._vertex_shader = VertexShader(_color_vertex_shader_program)

        if cls._fragment_shader is None:
            cls._fragment_shader = FragmentShader(_color_fragment_shader_program)

        if cls._program is None:
            cls._program = glshaders.compileProgram(
                cls._vertex_shader.shader, cls._fragment_shader.shader)

    @classmethod
    @property
    def source_pos_location(cls) -> int:
        if cls._source_pos_location is None:
            cls._source_pos_location = gl.glGetAttribLocation(cls.program, "vertex_source_position")
            if cls._source_pos_location == -1:
                raise ValueError("Could not find attribute")
        return cls._source_pos_location

    @classmethod
    @property
    def target_pos_location(cls) -> int:
        if cls._target_pos_location is None:
            cls._target_pos_location = gl.glGetAttribLocation(cls.program, "vertex_target_position")
            if cls._target_pos_location == -1:
                raise ValueError("Could not find attribute")
        return cls._target_pos_location

    @classmethod
    @property
    def tween_location(cls) -> int:
        if cls._tween_location is None:
            cls._tween_location = gl.glGetUniformLocation(cls.program, "tween")
            if cls._tween_location == -1:
                raise ValueError("Could not find attribute")
        return cls._tween_location

    @classmethod
    @property
    def model_view_projection_matrix(cls) -> int:
        if cls._model_view_projection_matrix_location is None:
            cls._model_view_projection_matrix_location = gl.glGetUniformLocation(cls.program,
                                                                                 "model_view_projection_matrix")
            if cls._model_view_projection_matrix_location == -1:
                raise ValueError("Could not find attribute")
        return cls._model_view_projection_matrix_location

    @classmethod
    def draw(cls, model_view_proj_matrix: NDArray[np.floating], vertex_array_object: TextureShaderVAO, tween: float):
        """Draws the texture using the vertex and index buffers."""
        try:
            gl.glUseProgram(cls.program)
            check_for_error()
            vertex_array_object.bind()

            tween = math.floor(time.time() % 2)
            gl.glUniform1f(cls.tween_location, tween)
            check_for_error()

            gl.glUniformMatrix4fv(cls.model_view_projection_matrix, 1, False, model_view_proj_matrix)
            check_for_error()

            gl.glDrawElements(gl.GL_TRIANGLES, vertex_array_object.num_elements, gl.GL_UNSIGNED_SHORT, None)
        finally:
            vertex_array_object.unbind()
            gl.glUseProgram(0)


class TextureShader(BaseShader):
    """
    This is a static class to contain our shaders. It is a singleton.
    """

    _texture_location: int | None = None

    _source_pos_location = None
    _target_pos_location = None
    _texture_coord_location = None
    _tween_location = None
    _model_view_projection_matrix_location = None
    _attributes: Sequence[VertexAttribute] | None = None

    @classmethod
    @property
    def get_attributes(cls) -> Sequence[VertexAttribute]:
        return (VertexAttribute(cls.source_pos_location, "vertex_source_position", 3, gl.GL_FLOAT, 4, 0),
                VertexAttribute(cls.target_pos_location, "vertex_target_position", 3, gl.GL_FLOAT, 4, 3),
                VertexAttribute(cls.texture_coord_location, "vertex_texture_coordinate", 2, gl.GL_FLOAT,
                                4, 6))

    @classmethod
    def initialize(cls):
        """initialize the static class.  This must be called AFTER the OpenGL context is created."""
        global _texture_vertex_shader_program
        global _texture_fragment_shader_program

        if cls._vertex_shader is None:
            cls._vertex_shader = VertexShader(_texture_vertex_shader_program)

        if cls._fragment_shader is None:
            cls._fragment_shader = FragmentShader(_texture_fragment_shader_program)

        if cls._program is None:
            cls._program = glshaders.compileProgram(
                cls._vertex_shader.shader, cls._fragment_shader.shader)

    @classmethod
    @property
    def source_pos_location(cls) -> int:
        if cls._source_pos_location is None:
            cls._source_pos_location = gl.glGetAttribLocation(cls.program, "vertex_source_position")
            if cls._source_pos_location == -1:
                raise ValueError("Could not find attribute")
        return cls._source_pos_location

    @classmethod
    @property
    def target_pos_location(cls) -> int:
        if cls._target_pos_location is None:
            cls._target_pos_location = gl.glGetAttribLocation(cls.program, "vertex_target_position")
            if cls._target_pos_location == -1:
                raise ValueError("Could not find attribute")
        return cls._target_pos_location

    @classmethod
    @property
    def texture_coord_location(cls) -> int:
        if cls._texture_coord_location is None:
            cls._texture_coord_location = gl.glGetAttribLocation(cls.program, "vertex_texture_coordinate")
            if cls._texture_coord_location == -1:
                raise ValueError("Could not find texture coordinate attribute")
        return cls._texture_coord_location

    @classmethod
    @property
    def texture_location(cls):
        if cls._texture_location is None:
            cls._texture_location = gl.glGetUniformLocation(cls.program, "texture")
            if cls._texture_location == -1:
                raise ValueError("Could not find texture attribute")
        return cls._texture_location

    @classmethod
    @property
    def tween_location(cls) -> int:
        if cls._tween_location is None:
            cls._tween_location = gl.glGetUniformLocation(cls.program, "tween")
            if cls._tween_location == -1:
                raise ValueError("Could not find attribute")
        return cls._tween_location

    @classmethod
    @property
    def model_view_projection_matrix_location(cls) -> int:
        if cls._model_view_projection_matrix_location is None:
            cls._model_view_projection_matrix_location = gl.glGetUniformLocation(cls.program,
                                                                                 "model_view_projection_matrix")
            if cls._model_view_projection_matrix_location == -1:
                raise ValueError("Could not find attribute")
        return cls._model_view_projection_matrix_location

    @classmethod
    def draw(cls, model_view_proj_matrix: NDArray[np.floating], texture: int, vertex_array_object: TextureShaderVAO,
             tween: float):
        """Draws the texture using the vertex and index buffers."""
        try:
            gl.glUseProgram(cls.program)
            check_for_error()
            vertex_array_object.bind()
            #
            # vertex_buffer.bind()
            # check_for_error()
            #
            # # TODO: I need to bind a vertex array object (VAO) to use index arrays
            # # https: // www.khronos.org / opengl / wiki / Vertex_Specification  # Vertex_Array_Object
            # gl.glEnableVertexAttribArray(cls.source_pos_location)
            # check_for_error()
            # gl.glEnableVertexAttribArray(cls.target_pos_location)
            # check_for_error()
            # gl.glEnableVertexAttribArray(cls.texture_coord_location)
            # check_for_error()
            #
            # # vao = gl.glGenVertexArrays(1)
            # # gl.glBindVertexArray(vao)
            #
            # stride = vertex_buffer.data.strides[0]
            # gl.glVertexAttribPointer(cls.source_pos_location, 3, gl.GL_FLOAT, False, stride, None)
            # check_for_error()
            # gl.glVertexAttribPointer(cls.target_pos_location, 3, gl.GL_FLOAT, False, stride, 3)
            # check_for_error()
            # gl.glVertexAttribPointer(cls.texture_coord_location, 2, gl.GL_FLOAT, False, stride, 6)
            # check_for_error()
            #
            # gl.glEnableClientState(gl.GL_VERTEX_ARRAY)
            # check_for_error()
            # gl.glEnableClientState(gl.GL_TEXTURE_COORD_ARRAY)
            # check_for_error()
            #
            # index_buffer.bind()
            # check_for_error()
            tween = math.floor(time.time() % 2)
            gl.glUniform1f(cls.tween_location, tween)
            check_for_error()
            gl.glUniformMatrix4fv(cls.model_view_projection_matrix_location, 1, False, model_view_proj_matrix)
            check_for_error()

            gl.glUniform1i(cls.texture_location, texture)
            check_for_error()

            gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_S, gl.GL_CLAMP_TO_BORDER)
            check_for_error()
            gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_T, gl.GL_CLAMP_TO_BORDER)
            check_for_error()
            gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_NEAREST)
            check_for_error()
            gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_NEAREST)
            check_for_error()

            gl.glDrawElements(gl.GL_TRIANGLES, vertex_array_object.num_elements, gl.GL_UNSIGNED_SHORT, None)
            check_for_error()
        finally:
            vertex_array_object.unbind()
            # gl.glDisableClientState(gl.GL_VERTEX_ARRAY)
            # gl.glDisableVertexAttribArray(cls.source_pos_location)
            # gl.glDisableVertexAttribArray(cls.target_pos_location)
            # gl.glDisableVertexAttribArray(cls.texture_coord_location)
            # #vertex_buffer.unbind()
            #
            # gl.glDisableClientState(gl.GL_INDEX_ARRAY)
            # index_buffer.unbind()
            gl.glUseProgram(0)
