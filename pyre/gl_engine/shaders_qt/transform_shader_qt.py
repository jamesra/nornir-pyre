from typing import Sequence

from OpenGL import GL as gl
import numpy as np
from numpy._typing import NDArray

from pyre.gl_engine import raise_on_error, check_for_error
from pyre.gl_engine.shader_vao import ShaderVAO
from pyre.gl_engine.shaders_qt.shader_base_qt import BaseShader, FragmentShader, VertexShader, bind_texture
from pyre.gl_engine.vertex_attribute import VertexAttribute
from pyre.gl_engine.vertexarraylayout import VertexArrayLayout

_transform_vertex_shader_program = """
        #version 330
        uniform float vert_tween; //The fractional amount of the tween between source and target space
        uniform mat4 model_view_projection_matrix;
        out vec2 frag_texture_coordinate;
        in vec3 vertex_source_position;
        in vec3 vertex_target_position;
        in vec2 vertex_texture_coordinate;
        void main(){
            gl_Position = model_view_projection_matrix * mix(vec4(vertex_source_position, 1),
                                                             vec4(vertex_target_position, 1),
                                                             vert_tween);
            frag_texture_coordinate = vertex_texture_coordinate;
        }
"""
_transform_fragment_shader_program = """
    #version 330
    uniform sampler2D source_texture;
    uniform sampler2D target_texture;
    uniform float texture_tween; //The fractional amount of the tween between source and target textures
    in vec2 frag_texture_coordinate;
    out vec4 outputColor;
    void main() {
        vec4 source_tex_color = texture(
                source_texture, frag_texture_coordinate
            ); 
        vec4 target_tex_color = texture(
                source_texture, frag_texture_coordinate
            );
        outputColor = mix(source_tex_color, target_tex_color, texture_tween); 
    }
"""


class TransformShader(BaseShader):
    """
    This is a shader that has a pair of verticies and textures for source/target space and can tween between them
    Using Qt's OpenGL system
    """

    _source_texture_location: int | None = None
    _target_texture_location: int | None = None

    _source_pos_location = None
    _target_pos_location = None
    _texture_coord_location = None
    _vertex_tween_location = None
    _texture_tween_location = None
    _model_view_projection_matrix_location = None
    _attributes: Sequence[VertexAttribute] | None = None

    def __init__(self):
        """initialize the static class.  This must be called AFTER the OpenGL context is created."""
        global _transform_vertex_shader_program
        global _transform_fragment_shader_program

        self._vertex_layout = VertexArrayLayout(
            [VertexAttribute(lambda: self.source_pos_location, "vertex_source_position", 3, gl.GL_FLOAT),
             VertexAttribute(lambda: self.target_pos_location, "vertex_target_position", 3, gl.GL_FLOAT),
             VertexAttribute(lambda: self.texture_coord_location, "vertex_texture_coordinate", 2, gl.GL_FLOAT)])

        self._vertex_shader = VertexShader(_transform_vertex_shader_program)
        self._fragment_shader = FragmentShader(_transform_fragment_shader_program)

    def initialize_gl_objects(self):
        super().initialize_gl_objects()

    @property
    def source_pos_location(self) -> int:
        if self._source_pos_location is None:
            self._source_pos_location = self.program.attributeLocation("vertex_source_position")
            if self._source_pos_location == -1:
                raise ValueError("Could not find attribute")
        return self._source_pos_location

    @property
    def target_pos_location(self) -> int:
        if self._target_pos_location is None:
            self._target_pos_location = self.program.attributeLocation("vertex_target_position")
            if self._target_pos_location == -1:
                raise ValueError("Could not find attribute")
        return self._target_pos_location

    @property
    def texture_coord_location(self) -> int:
        if self._texture_coord_location is None:
            self._texture_coord_location = self.program.attributeLocation("vertex_texture_coordinate")
            if self._texture_coord_location == -1:
                raise ValueError("Could not find texture coordinate attribute")
        return self._texture_coord_location

    @property
    def source_texture_location(self):
        if self._source_texture_location is None:
            self._source_texture_location = self.program.uniformLocation("source_texture")
            if self._source_texture_location == -1:
                raise ValueError("Could not find texture_sampler attribute")
        return self._source_texture_location

    @property
    def target_texture_location(self):
        if self._target_texture_location is None:
            self._target_texture_location = self.program.uniformLocation("target_texture")
            if self._target_texture_location == -1:
                raise ValueError("Could not find texture_sampler attribute")
        return self._target_texture_location

    @property
    def vertex_tween_location(self) -> int:
        if self._vertex_tween_location is None:
            self._vertex_tween_location = self.program.uniformLocation("vert_tween")
            if self._vertex_tween_location == -1:
                raise ValueError("Could not find attribute")
        return self._vertex_tween_location

    @property
    def texture_tween_location(self) -> int:
        if self._texture_tween_location is None:
            self._texture_tween_location = self.program.uniformLocation("texture_tween")
            if self._texture_tween_location == -1:
                raise ValueError("Could not find attribute")
        return self._texture_tween_location

    @property
    def model_view_projection_matrix_location(self) -> int:
        if self._model_view_projection_matrix_location is None:
            self._model_view_projection_matrix_location = self.program.uniformLocation("model_view_projection_matrix")
            if self._model_view_projection_matrix_location == -1:
                raise ValueError("Could not find attribute")
        return self._model_view_projection_matrix_location

    def draw(self, model_view_proj_matrix: NDArray[np.floating], source_texture: int, target_texture: int,
             vertex_array_object: ShaderVAO,
             vertex_tween: float, texture_tween: float):
        """Draws the texture using the vertex and index buffers.
        :param model_view_proj_matrix: The model view projection matrix
        :param source_texture: The source texture
        :param target_texture: The target texture
        :param vertex_array_object: The vertex array object with verticies defined for source and target space verticies and texture coordinates
        :param vertex_tween: The fractional amount of the tween between source and target space for verticies
        :param texture_tween: The fractional amount of the tween between source and target textures
        """
        try:
            # Check for errors from previous operations before starting draw
            raise_on_error("at start of transform_shader.draw")
            
            # Use the shader program
            self.program.bind()
            raise_on_error("after program.bind() in draw")
            
            # When using raw OpenGL calls (glUniform*), we need to ensure glUseProgram is called
            program_id = self.program.programId()
            gl.glUseProgram(program_id)
            raise_on_error("after glUseProgram in draw")
            
            vertex_array_object.bind()

            # Bind textures
            bind_texture(source_texture, self.source_texture_location, gl.GL_TEXTURE0)
            bind_texture(target_texture, self.target_texture_location, gl.GL_TEXTURE1)

            # Set uniform values
            self.program.setUniformValue(self.vertex_tween_location, vertex_tween)
            raise_on_error("after setUniformValue(vertex_tween) in draw")

            self.program.setUniformValue(self.texture_tween_location, texture_tween)
            raise_on_error("after setUniformValue(texture_tween) in draw")

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

            gl.glDrawElements(gl.GL_TRIANGLES, vertex_array_object.num_elements, gl.GL_UNSIGNED_SHORT, None)
            raise_on_error("after glDrawElements in draw")
        finally:
            check_for_error("in draw finally block")
            vertex_array_object.unbind()
            self.program.release()
