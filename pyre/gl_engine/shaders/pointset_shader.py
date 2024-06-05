from typing import Sequence

from OpenGL import GL as gl
from OpenGL.GL import shaders as glshaders
import numpy as np
from numpy._typing import NDArray

from pyre.gl_engine import check_for_error
from pyre.gl_engine.shaders.shader_base import VertexShader, FragmentShader, BaseShader
from pyre.gl_engine.instanced_vao import InstancedVAO
from pyre.gl_engine.vertex_attribute import VertexAttribute
from pyre.gl_engine.vertexarraylayout import VertexArrayLayout

_pointset_vertex_shader_program = """
        #version 330
        uniform float tween; //The fractional amount of the tween between source and target space
        uniform mat4 view_projection_matrix;
        out vec2 frag_texture_coordinate;
        in vec3 vertex_position; // Verticies for a square centered at the origin 
        in vec2 vertex_texture_coordinate;
        in vec2 point_source_offset; //The position of the point in source space
        in vec2 point_target_offset; //The position of the point in target space
        void main(){
            vec3 translated_target_pos = vertex_position + vec3(point_target_offset.x, point_target_offset.y, 0);
            vec3 translated_source_pos = vertex_position + vec3(point_source_offset.x, point_source_offset.y, 0);
            gl_Position = view_projection_matrix * mix(vec4(translated_source_pos, 1),
                                                             vec4(translated_target_pos, 1),
                                                             tween);
            frag_texture_coordinate = vertex_texture_coordinate;
        }
"""

_pointset_fragment_shader_program = """
    #version 330
    uniform sampler2D texture_sampler;
    in vec2 frag_texture_coordinate;
    out vec4 outputColor;
    void main() {
        vec4 texColor = texture(
                texture_sampler, frag_texture_coordinate
            ); 
        // outputColor = vec4(texColor.r, frag_texture_coordinate.x, frag_texture_coordinate.y, 1);
        outputColor = texColor;
    }
"""


class PointSetShader(BaseShader):
    """
    This shader renders a set of points with a texture centered on each point
    """

    _texture_sampler_location: int | None = None

    _vertex_location: int | None = None
    _vertex_texture_location: int | None = None
    _point_source_offset_location: int | None = None
    _point_target_offset_location: int | None = None
    _tween_location: int | None = None
    _view_projection_matrix_location: int | None = None
    _attributes: Sequence[VertexAttribute] | None = None
    _vertex_layout: VertexArrayLayout | None = None
    _pointset_layout: VertexArrayLayout | None = None

    @property
    def vertex_layout(self) -> VertexArrayLayout:
        """The layout of the vertex buffer"""
        return self._vertex_layout

    @property
    def pointset_layout(self) -> VertexArrayLayout:
        """
        The layout for the pointset buffer.
        SourceX, SourceY, TargetX, TargetY for each point
        """
        return self._pointset_layout

    def __init__(self):
        """initialize the static class.  This must be called AFTER the OpenGL context is created."""
        global _pointset_vertex_shader_program
        global _pointset_fragment_shader_program

        self._vertex_layout = VertexArrayLayout(
            [VertexAttribute(lambda: self.vertex_location, "vertex_position", 3, gl.GL_FLOAT),
             VertexAttribute(lambda: self.texture_coord_location, "vertex_texture_coordinate", 2, gl.GL_FLOAT)])

        self._pointset_layout = VertexArrayLayout(
            [VertexAttribute(lambda: self.point_source_offset_location, "point_source_offset", 2, gl.GL_FLOAT,
                             instanced=True),
             VertexAttribute(lambda: self.point_target_offset_location, "point_target_offset", 2, gl.GL_FLOAT,
                             instanced=True)])

        self._vertex_shader = VertexShader(_pointset_vertex_shader_program)
        self._fragment_shader = FragmentShader(_pointset_fragment_shader_program)

    def initialize_gl_objects(self):
        super().initialize_gl_objects()

    @property
    def vertex_location(self) -> int:
        if self._vertex_location is None:
            self._vertex_location = gl.glGetAttribLocation(self.program, "vertex_position")
            if self._vertex_location == -1:
                raise ValueError("Could not find attribute")
        return self._vertex_location

    @property
    def texture_coord_location(self) -> int:
        if self._vertex_texture_location is None:
            self._vertex_texture_location = gl.glGetAttribLocation(self.program, "vertex_texture_coordinate")
            if self._vertex_texture_location == -1:
                raise ValueError("Could not find texture coordinate attribute")
        return self._vertex_texture_location

    @property
    def point_source_offset_location(self) -> int:
        if self._point_source_offset_location is None:
            self._point_source_offset_location = gl.glGetAttribLocation(self.program, "point_source_offset")
            if self._point_source_offset_location == -1:
                raise ValueError("Could not find attribute")
        return self._point_source_offset_location

    @property
    def point_target_offset_location(self) -> int:
        if self._point_target_offset_location is None:
            self._point_target_offset_location = gl.glGetAttribLocation(self.program, "point_target_offset")
            if self._point_target_offset_location == -1:
                raise ValueError("Could not find attribute")
        return self._point_target_offset_location

    @property
    def texture_sampler(self):
        if self._texture_sampler_location is None:
            self._texture_sampler_location = gl.glGetUniformLocation(self.program, "texture_sampler")
            if self._texture_sampler_location == -1:
                raise ValueError("Could not find texture_sampler attribute")
        return self._texture_sampler_location

    @property
    def tween_location(self) -> int:
        if self._tween_location is None:
            self._tween_location = gl.glGetUniformLocation(self.program, "tween")
            if self._tween_location == -1:
                raise ValueError("Could not find attribute")
        return self._tween_location

    @property
    def model_view_projection_matrix_location(self) -> int:
        if self._view_projection_matrix_location is None:
            self._view_projection_matrix_location = gl.glGetUniformLocation(self.program,
                                                                            "view_projection_matrix")
            if self._view_projection_matrix_location == -1:
                raise ValueError("Could not find attribute")
        return self._view_projection_matrix_location

    def draw(self, model_view_proj_matrix: NDArray[np.floating],
             texture: int,
             vao: InstancedVAO,
             num_instances: int,
             tween: float):
        """Draws the texture using the vertex and index buffers."""
        try:
            gl.glUseProgram(self.program)
            check_for_error()
            vao.bind()

            gl.glActiveTexture(gl.GL_TEXTURE0)
            check_for_error()
            gl.glBindTexture(gl.GL_TEXTURE_2D, texture)
            check_for_error()
            gl.glUniform1i(self.texture_sampler, 0)
            check_for_error()

            # tween = math.floor(time.time() % 2)
            # tween = (time.time() % 15) / 15.0
            gl.glUniform1f(self.tween_location, tween)
            check_for_error()
            gl.glUniformMatrix4fv(self.model_view_projection_matrix_location, 1, False,
                                  model_view_proj_matrix.astype(np.float32))
            check_for_error()

            # status = gl.glCheckFramebufferStatus(gl.GL_FRAMEBUFFER)
            # if status != gl.GL_FRAMEBUFFER_COMPLETE:
            #    print("Framebuffer is not complete")
            gl.glDrawElementsInstanced(gl.GL_TRIANGLES, vao.num_elements,
                                       gl.GL_UNSIGNED_SHORT,
                                       None, num_instances)
            check_for_error()
        finally:
            check_for_error()
            vao.unbind()
            gl.glUseProgram(0)
