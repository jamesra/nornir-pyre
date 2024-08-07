from typing import Sequence
import warnings

from OpenGL import GL as gl
from OpenGL.GL import shaders as glshaders
import numpy as np
from numpy._typing import NDArray

from pyre.gl_engine import check_for_error, IVAO
from pyre.gl_engine.shaders.shader_base import BaseShader, VertexShader, FragmentShader
from pyre.gl_engine.shader_vao import ShaderVAO
from pyre.gl_engine.vertex_attribute import VertexAttribute
from pyre.gl_engine.vertexarraylayout import VertexArrayLayout

_texture_vertex_shader_program = """
        #version 330
        uniform float tween; //The fractional amount of the tween between source and target space
        uniform mat4 model_view_projection_matrix;
        out vec2 frag_texture_coordinate;
        in vec3 vertex_source_position;
        in vec3 vertex_target_position;
        in vec2 vertex_texture_coordinate;
        void main(){
            gl_Position = model_view_projection_matrix * mix(vec4(vertex_source_position, 1),
                                                             vec4(vertex_target_position, 1),
                                                             tween);
            frag_texture_coordinate = vertex_texture_coordinate;  
        }
"""
_texture_fragment_shader_program = """
    #version 330
    uniform sampler2D texture_sampler;
    in vec2 frag_texture_coordinate;
    out vec4 outputColor;
    void main() {
        vec4 texColor = texture(
                texture_sampler, frag_texture_coordinate
            ); 
        //outputColor = vec4(texColor.r, frag_texture_coordinate.x, frag_texture_coordinate.y, 1);
        outputColor = texColor;
    }
"""


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

    def __init__(self):
        """initialize the static class.  This must be called AFTER the OpenGL context is created."""
        global _texture_vertex_shader_program
        global _texture_fragment_shader_program

        self._vertex_layout = VertexArrayLayout(
            [VertexAttribute(lambda: self.target_pos_location, "vertex_target_position", 3, gl.GL_FLOAT),
             VertexAttribute(lambda: self.source_pos_location, "vertex_source_position", 3, gl.GL_FLOAT),
             VertexAttribute(lambda: self.texture_coord_location, "vertex_texture_coordinate", 2, gl.GL_FLOAT)])

        self._vertex_shader = VertexShader(_texture_vertex_shader_program)
        self._fragment_shader = FragmentShader(_texture_fragment_shader_program)

    def initialize_gl_objects(self):
        super().initialize_gl_objects()

    @property
    def source_pos_location(self) -> int:
        if self._source_pos_location is None:
            self._source_pos_location = gl.glGetAttribLocation(self.program, "vertex_source_position")
            if self._source_pos_location == -1:
                raise ValueError("Could not find attribute")
        return self._source_pos_location

    @property
    def target_pos_location(self) -> int:
        if self._target_pos_location is None:
            self._target_pos_location = gl.glGetAttribLocation(self.program, "vertex_target_position")
            if self._target_pos_location == -1:
                raise ValueError("Could not find attribute")
        return self._target_pos_location

    @property
    def texture_coord_location(self) -> int:
        if self._texture_coord_location is None:
            self._texture_coord_location = gl.glGetAttribLocation(self.program, "vertex_texture_coordinate")
            if self._texture_coord_location == -1:
                raise ValueError("Could not find texture coordinate attribute")
        return self._texture_coord_location

    @property
    def texture_location(self):
        if self._texture_location is None:
            self._texture_location = gl.glGetUniformLocation(self.program, "texture_sampler")
            if self._texture_location == -1:
                raise ValueError("Could not find texture_sampler attribute")
        return self._texture_location

    @property
    def tween_location(self) -> int:
        if self._tween_location is None:
            self._tween_location = gl.glGetUniformLocation(self.program, "tween")
            if self._tween_location == -1:
                raise ValueError("Could not find attribute")
        return self._tween_location

    @property
    def model_view_projection_matrix_location(self) -> int:
        if self._model_view_projection_matrix_location is None:
            self._model_view_projection_matrix_location = gl.glGetUniformLocation(self.program,
                                                                                  "model_view_projection_matrix")
            if self._model_view_projection_matrix_location == -1:
                raise ValueError("Could not find attribute")
        return self._model_view_projection_matrix_location

    def draw(self, model_view_proj_matrix: NDArray[np.floating], texture: int, vertex_array_object: IVAO,
             tween: float):
        """Draws the texture using the vertex and index buffers."""
        try:
            gl.glUseProgram(self.program)
            check_for_error()

            gl.glActiveTexture(gl.GL_TEXTURE0)
            check_for_error()
            gl.glBindTexture(gl.GL_TEXTURE_2D, texture)
            check_for_error()

            vertex_array_object.bind()

            gl.glUniform1f(self.tween_location, tween)
            check_for_error()
            gl.glUniform1i(self.texture_location, 0)
            check_for_error()

            # tween = math.floor(time.time() % 2)
            # tween = (time.time() % 15) / 15.0
            gl.glUniformMatrix4fv(self.model_view_projection_matrix_location, 1, False,
                                  model_view_proj_matrix.astype(np.float32, copy=False))
            check_for_error()

            # status = gl.glCheckFramebufferStatus(gl.GL_FRAMEBUFFER)
            # if status != gl.GL_FRAMEBUFFER_COMPLETE:
            #    print("Framebuffer is not complete")

            if vertex_array_object.num_elements == 0:
                warnings.warn("No elements to draw")
            gl.glDrawElements(gl.GL_TRIANGLES, vertex_array_object.num_elements, gl.GL_UNSIGNED_SHORT, None)
            check_for_error()
        finally:
            check_for_error()
            vertex_array_object.unbind()
            # gl.glDisableClientState(gl.GL_VERTEX_ARRAY)
            # gl.glDisableVertexAttribArray(self.source_pos_location)
            # gl.glDisableVertexAttribArray(self.target_pos_location)
            # gl.glDisableVertexAttribArray(self.texture_coord_location)
            # #vertex_buffer.unbind()
            #
            # gl.glDisableClientState(gl.GL_INDEX_ARRAY)
            # index_buffer.unbind()
            gl.glUseProgram(0)
