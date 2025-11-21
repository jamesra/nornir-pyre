from typing import Sequence

from OpenGL import GL as gl
import numpy as np
from numpy._typing import NDArray

from pyre.gl_engine import raise_on_error, check_for_error
from pyre.gl_engine.instanced_vao import InstancedVAO
from pyre.gl_engine.shaders_qt.shader_base_qt import BaseShader, FragmentShader, VertexShader
from pyre.gl_engine.vertex_attribute import VertexAttribute
from pyre.gl_engine.vertexarraylayout import VertexArrayLayout

_controlpointset_vertex_shader_program = """
        #version 450
        uniform float tween; //The fractional amount of the tween between source and target space
        uniform mat4 view_projection_matrix;
        uniform float scale; //The scale of the points
        out vec2 frag_texture_coordinate;
        in vec3 vertex_position; // Verticies for a square centered at the origin 
        in vec2 vertex_texture_coordinate;
        in vec2 point_source_offset; //The position of the point in source space
        in vec2 point_target_offset; //The position of the point in target space
        in float texture_index; //The index of the texture to use
        out float frag_texture_index;
        
        mat4 BuildTranslation(vec3 delta)
        {
            return mat4(
                vec4(1.0, 0.0, 0.0, 0.0),
                vec4(0.0, 1.0, 0.0, 0.0),
                vec4(0.0, 0.0, 1.0, 0.0),
                vec4(delta, 1.0));
        }
        
        mat4 BuildScaleTranslation(float scale, vec3 delta)
        {
            return mat4(
                vec4(scale, 0.0, 0.0, 0.0),
                vec4(0.0, scale, 0.0, 0.0),
                vec4(0.0, 0.0, 1.0, 0.0),
                vec4(delta, 1.0));
        }

        void main(){ 
            vec3 blended_offset_pos = mix(vec3(point_source_offset, 1),
                                   vec3(point_target_offset, 1),
                                   tween);
            mat4 translate_matrix;
            translate_matrix = BuildScaleTranslation(scale, blended_offset_pos);
            mat4 model_view_proj;
            model_view_proj =  view_projection_matrix * translate_matrix; 
            gl_Position = model_view_proj * vec4(vertex_position, 1.0);
            frag_texture_coordinate = vertex_texture_coordinate;
            frag_texture_index = texture_index;
        }
"""

_controlpointset_fragment_shader_program = """
    #version 450
    uniform sampler2DArray texture_sampler;
    in vec2 frag_texture_coordinate;
    in float frag_texture_index;
    out vec4 outputColor;
    void main() {
        vec4 texColor = texture(
                texture_sampler, vec3(frag_texture_coordinate, frag_texture_index)
            ); 
        // outputColor = vec4(texColor.r, frag_texture_coordinate.x, frag_texture_coordinate.y, 1);
        //outputColor = vec4(frag_texture_index, texColor.g, texColor.b, 1);
        outputColor = texColor;
    }
"""


class ControlPointSetShader(BaseShader):
    """
    This shader renders a set of points with a texture centered on each point
    Using Qt's OpenGL system
    """

    _texture_sampler_location: int | None = None

    _vertex_location: int | None = None
    _vertex_texture_location: int | None = None
    _point_source_offset_location: int | None = None
    _point_target_offset_location: int | None = None
    _tween_location: int | None = None
    _scale_location: int | None = None
    _view_projection_matrix_location: int | None = None
    _attributes: Sequence[VertexAttribute] | None = None
    _vertex_layout: VertexArrayLayout | None = None
    _pointset_layout: VertexArrayLayout | None = None
    _texture_index_location: int | None = None  # Index of the texture the instance should use

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

    @property
    def texture_index_layout(self) -> VertexArrayLayout:
        """
        The layout for the texture index buffer.
        """
        return self._texture_index_layout

    def __init__(self):
        """initialize the static class.  This must be called AFTER the OpenGL context is created."""
        global _controlpointset_vertex_shader_program
        global _controlpointset_fragment_shader_program

        self._vertex_layout = VertexArrayLayout(
            [VertexAttribute(lambda: self.vertex_location, "vertex_position", 3, gl.GL_FLOAT),
             VertexAttribute(lambda: self.texture_coord_location, "vertex_texture_coordinate", 2, gl.GL_FLOAT)])

        self._pointset_layout = VertexArrayLayout(
            [VertexAttribute(lambda: self.point_target_offset_location, "point_target_offset", 2, gl.GL_FLOAT,
                             instanced=True),
             VertexAttribute(lambda: self.point_source_offset_location, "point_source_offset", 2, gl.GL_FLOAT,
                             instanced=True),
             ])

        self._texture_index_layout = VertexArrayLayout(
            [VertexAttribute(lambda: self.texture_index_location, "texture_index", 1, gl.GL_FLOAT,
                             instanced=True)])

        self._vertex_shader = VertexShader(_controlpointset_vertex_shader_program)

        self._fragment_shader = FragmentShader(_controlpointset_fragment_shader_program)

    def initialize_gl_objects(self):
        super().initialize_gl_objects()

    @property
    def texture_index_location(self) -> int:
        if self._texture_index_location is None:
            self._texture_index_location = self.program.attributeLocation("texture_index")
            if self._texture_index_location == -1:
                raise ValueError("Could not find attribute")
        return self._texture_index_location

    @property
    def vertex_location(self) -> int:
        if self._vertex_location is None:
            self._vertex_location = self.program.attributeLocation("vertex_position")
            if self._vertex_location == -1:
                raise ValueError("Could not find attribute")
        return self._vertex_location

    @property
    def texture_coord_location(self) -> int:
        if self._vertex_texture_location is None:
            self._vertex_texture_location = self.program.attributeLocation("vertex_texture_coordinate")
            if self._vertex_texture_location == -1:
                raise ValueError("Could not find texture coordinate attribute")
        return self._vertex_texture_location

    @property
    def point_source_offset_location(self) -> int:
        if self._point_source_offset_location is None:
            self._point_source_offset_location = self.program.attributeLocation("point_source_offset")
            if self._point_source_offset_location == -1:
                raise ValueError("Could not find attribute")
        return self._point_source_offset_location

    @property
    def point_target_offset_location(self) -> int:
        if self._point_target_offset_location is None:
            self._point_target_offset_location = self.program.attributeLocation("point_target_offset")
            if self._point_target_offset_location == -1:
                raise ValueError("Could not find attribute")
        return self._point_target_offset_location

    @property
    def texture_sampler(self):
        if self._texture_sampler_location is None:
            self._texture_sampler_location = self.program.uniformLocation("texture_sampler")
            if self._texture_sampler_location == -1:
                raise ValueError("Could not find texture_sampler attribute")
        return self._texture_sampler_location

    @property
    def tween_location(self) -> int:
        if self._tween_location is None:
            self._tween_location = self.program.uniformLocation("tween")
            if self._tween_location == -1:
                raise ValueError("Could not find attribute")
        return self._tween_location

    @property
    def scale_location(self) -> int:
        if self._scale_location is None:
            self._scale_location = self.program.uniformLocation("scale")
            if self._scale_location == -1:
                raise ValueError("Could not find attribute")
        return self._scale_location

    @property
    def model_view_projection_matrix_location(self) -> int:
        if self._view_projection_matrix_location is None:
            self._view_projection_matrix_location = self.program.uniformLocation("view_projection_matrix")
            if self._view_projection_matrix_location == -1:
                raise ValueError("Could not find attribute")
        return self._view_projection_matrix_location

    def draw(self, model_view_proj_matrix: NDArray[np.floating],
             texture: int,
             vao: InstancedVAO,
             num_instances: int,
             scale: float,
             tween: float):
        """Draws the texture using the vertex and index buffers."""
        if num_instances == 0:
            return

        try:
            # Check for errors from previous operations before starting draw
            raise_on_error("at start of controlpointset_shader.draw")
            
            # Use the shader program
            self.program.bind()
            raise_on_error("after program.bind() in draw")
            
            # When using raw OpenGL calls (glUniform*), we need to ensure glUseProgram is called
            program_id = self.program.programId()
            gl.glUseProgram(program_id)
            raise_on_error("after glUseProgram in draw")

            if not vao.bind():
                return  # Skip drawing if the vao isn't able to bind (May be invalid)

            # Set the active texture and bind it
            gl.glActiveTexture(gl.GL_TEXTURE0)
            raise_on_error("after glActiveTexture in draw")
            gl.glBindTexture(gl.GL_TEXTURE_2D_ARRAY, texture)
            raise_on_error("after glBindTexture in draw")

            # Set uniform values
            self.program.setUniformValue(self.texture_sampler, 0)
            raise_on_error("after setUniformValue(texture_sampler) in draw")

            self.program.setUniformValue(self.tween_location, tween)
            raise_on_error("after setUniformValue(tween) in draw")

            self.program.setUniformValue(self.scale_location, scale)
            raise_on_error("after setUniformValue(scale) in draw")

            # Set the model-view-projection matrix
            # PyQt6's setUniformValueArray has a different signature, so use raw OpenGL
            location = self.model_view_projection_matrix_location
            if location == -1:
                raise ValueError("model_view_projection_matrix uniform not found in shader")
            
            matrix_data = np.ascontiguousarray(
                model_view_proj_matrix.astype(np.float32).flatten(),
                dtype=np.float32
            )
            if len(matrix_data) != 16:
                raise ValueError(f"Matrix must have 16 elements, got {len(matrix_data)}")
            
            gl.glUniformMatrix4fv(
                location,
                1,  # count (1 matrix)
                gl.GL_TRUE,  # transpose=True (numpy is row-major, OpenGL expects column-major)
                matrix_data
            )
            raise_on_error("after glUniformMatrix4fv in draw")

            # Draw the instances
            gl.glDrawElementsInstanced(gl.GL_TRIANGLES, vao.num_elements,
                                       gl.GL_UNSIGNED_SHORT,
                                       None, num_instances)
            raise_on_error("after glDrawElementsInstanced in draw")
        finally:
            check_for_error("in draw finally block")
            vao.unbind()
            self.program.release()
