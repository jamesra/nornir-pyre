"""
Displays two textures and overlays them with a blend function
"""
from typing import Sequence
from enum import Enum
import warnings

from OpenGL import GL as gl
from OpenGL.GL import shaders as glshaders
import numpy as np
from numpy._typing import NDArray

from pyre.gl_engine import check_for_error
from pyre.gl_engine.shaders.shader_base import VertexShader, FragmentShader, BaseShader, bind_texture
from pyre.gl_engine.shader_vao import ShaderVAO
from pyre.gl_engine.vertex_attribute import VertexAttribute
from pyre.gl_engine.vertexarraylayout import VertexArrayLayout

# Define vertices for a full-screen quad
full_screen_vertices = np.array([
    -1.0, -1.0, 0.0, 0.0, 0.0,  # Bottom-left corner
    1.0, -1.0, 0.0, 1.0, 0.0,  # Bottom-right corner
    1.0, 1.0, 0.0, 1.0, 1.0,  # Top-right corner
    -1.0, 1.0, 0.0, 0.0, 1.0  # Top-left corner
], dtype=np.float32)

# Define indices for the quad (two triangles)
full_screen_indices = np.array([
    0, 1, 2,  # First triangle
    2, 3, 0  # Second triangle
], dtype=np.uint32)

_overlay_vertex_shader_program = """
        #version 450
        uniform mat4 model_view_projection_matrix; //Should be identity matrix to render 1:1 from an Frame Buffer Object texture directly back to same coordinates on a back buffer
        out vec2 frag_texture_coordinate;
        in vec3 vertex_position; 
        in vec2 vertex_texture_coordinate;
        void main(){
            gl_Position = model_view_projection_matrix * vec4(vertex_position, 1);
            frag_texture_coordinate = vertex_texture_coordinate;
        }
"""

_overlay_channel_mix_texture_fragment_shader_program = """
    #version 450
    uniform sampler2D target_texture;
    uniform sampler2D source_texture;
    uniform vec4 source_channel_blend; //We add each textures data to the channel.  Determines how much to scale each channel before copying to output color
    uniform vec4 target_channel_blend;
    in vec2 frag_texture_coordinate;
    out vec4 outputColor;
    void main() {
        vec4 source_tex_color = texture(source_texture, frag_texture_coordinate) * source_channel_blend; 
        vec4 target_tex_color = texture(target_texture, frag_texture_coordinate) * target_channel_blend;
        outputColor = clamp(vec4(source_tex_color.r + target_tex_color.r,
                                 source_tex_color.g + target_tex_color.g,
                                 source_tex_color.b + target_tex_color.b,
                                 source_tex_color.a + target_tex_color.a), 0, 1);
    }
"""


class OverlayType(Enum):
    Tween = 0,  # Blend the textures using the tween value
    ChannelDodge = 1,  # Put textures into separate channels
    Difference = 2,  # Subtract one texture from another


class OverlayShader(BaseShader):
    """
    This is a shader that has a pair of verticies and textures for source/target space and can tween between them
    """

    _source_texture_location: int | None = None
    _target_texture_location: int | None = None

    _source_channel_blend_location: int | None = None
    _target_channel_blend_location: int | None = None

    _vertex_position_location = None
    _target_pos_location = None
    _texture_coord_location = None
    _model_view_projection_matrix_location = None
    _attributes: Sequence[VertexAttribute] | None = None

    _fragment_shaders: dict[OverlayType, int]
    _programs: dict[OverlayType, int]  # lookup a program to use based on overlay type

    _vao: ShaderVAO | None  # Vertex array object for this shader.  All shaders can share verticies since we simply copy two textures directly to the back buffer.

    def __init__(self):
        """initialize the static class.  This must be called AFTER the OpenGL context is created."""
        global _overlay_vertex_shader_program
        global _overlay_channel_mix_texture_fragment_shader_program

        self._vertex_layout = VertexArrayLayout(
            [VertexAttribute(lambda: self.vertex_position_location, "vertex_position", 3, gl.GL_FLOAT),
             VertexAttribute(lambda: self.texture_coord_location, "vertex_texture_coordinate", 2, gl.GL_FLOAT)])

        self._vao = None
        self._vertex_shader = VertexShader(_overlay_vertex_shader_program)
        self._fragment_shader = FragmentShader(_overlay_channel_mix_texture_fragment_shader_program)

        self._programs = {}

    def initialize_gl_objects(self):
        super().initialize_gl_objects()

        # for overlay_type, fragment_shader in self._fragment_shaders.items():
        #    self._programs[overlay_type] = glshaders.compileProgram(self._vertex_shader.shader, fragment_shader)

        # Create our vertex array object if it is not initialized
        if self._vao is None:
            self._vao = self.create_vao()

    @property
    def vertex_position_location(self) -> int:
        if self._vertex_position_location is None:
            self._vertex_position_location = gl.glGetAttribLocation(self.program, "vertex_position")
            if self._vertex_position_location == -1:
                raise ValueError("Could not find attribute")
        return self._vertex_position_location

    @property
    def texture_coord_location(self) -> int:
        if self._texture_coord_location is None:
            self._texture_coord_location = gl.glGetAttribLocation(self.program, "vertex_texture_coordinate")
            if self._texture_coord_location == -1:
                raise ValueError("Could not find texture coordinate attribute")
        return self._texture_coord_location

    @property
    def source_texture_location(self):
        if self._source_texture_location is None:
            self._source_texture_location = gl.glGetUniformLocation(self.program, "source_texture")
            if self._source_texture_location == -1:
                raise ValueError("Could not find texture_sampler attribute")
        return self._source_texture_location

    @property
    def target_texture_location(self):
        if self._target_texture_location is None:
            self._target_texture_location = gl.glGetUniformLocation(self.program, "target_texture")
            if self._target_texture_location == -1:
                raise ValueError("Could not find texture_sampler attribute")
        return self._target_texture_location

    @property
    def model_view_projection_matrix_location(self) -> int:
        if self._model_view_projection_matrix_location is None:
            self._model_view_projection_matrix_location = gl.glGetUniformLocation(self.program,
                                                                                  "model_view_projection_matrix")
            if self._model_view_projection_matrix_location == -1:
                raise ValueError("Could not find attribute")
        return self._model_view_projection_matrix_location

    @property
    def source_channel_blend_location(self) -> int:
        if self._source_channel_blend_location is None:
            self._source_channel_blend_location = gl.glGetUniformLocation(self.program,
                                                                          "source_channel_blend")
            if self._source_channel_blend_location == -1:
                raise ValueError("Could not find attribute")
        return self._source_channel_blend_location

    @property
    def target_channel_blend_location(self) -> int:
        if self._target_channel_blend_location is None:
            self._target_channel_blend_location = gl.glGetUniformLocation(self.program,
                                                                          "target_channel_blend")
            if self._target_channel_blend_location == -1:
                raise ValueError("Could not find attribute")
        return self._target_channel_blend_location

    def create_vao(self) -> ShaderVAO:
        """
        Creates a VertexArrayObject for the overlay shader.
        """
        return ShaderVAO(self._vertex_layout,
                         full_screen_vertices,
                         full_screen_indices)

    def draw(self,
             model_view_proj_matrix: NDArray[np.floating],
             source_texture: int, target_texture: int,
             overlay_type: OverlayType | None,
             source_channel_mix: NDArray[np.floating],
             target_channel_mix: NDArray[np.floating]):
        """Draws the texture using the vertex and index buffers.
        :param model_view_proj_matrix: The model view projection matrix
        :param source_texture: The source texture
        :param target_texture: The target texture
        :param vertex_array_object: The vertex array object with verticies defined for source and target space verticies and texture coordinates
        :param vertex_tween: The fractional amount of the tween between source and target space for verticies
        :param texture_tween: The fractional amount of the tween between source and target textures
        """
        try:
            if overlay_type is None:
                gl.glUseProgram(self.program)
            else:
                gl.glUseProgram(self._programs[overlay_type])

            check_for_error()
            self._vao.bind()

            bind_texture(source_texture, self.source_texture_location, gl.GL_TEXTURE0)
            bind_texture(target_texture, self.target_texture_location, gl.GL_TEXTURE1)

            gl.glUniform4fv(self.source_channel_blend_location, 1, source_channel_mix.astype(np.float32, copy=False))
            check_for_error()
            gl.glUniform4fv(self.target_channel_blend_location, 1, target_channel_mix.astype(np.float32, copy=False))
            check_for_error()
            gl.glUniformMatrix4fv(self.model_view_projection_matrix_location, 1, False,
                                  model_view_proj_matrix.astype(np.float32, copy=False))
            check_for_error()

            if self._vao.num_elements == 0:
                warnings.warn("No elements to draw")
            gl.glDrawElements(gl.GL_TRIANGLES, self._vao.num_elements, gl.GL_UNSIGNED_SHORT, None)
            check_for_error()
        finally:
            check_for_error()
            self._vao.unbind()
            gl.glUseProgram(0)
