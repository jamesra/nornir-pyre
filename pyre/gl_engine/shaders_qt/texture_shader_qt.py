from typing import Sequence
import warnings

from OpenGL import GL as gl
import numpy as np
from numpy._typing import NDArray
from PyQt6.QtGui import QMatrix4x4
import nornir_imageregistration

from pyre.gl_engine import IVAO, raise_on_error, check_for_error
from pyre.gl_engine.shaders_qt.shader_base_qt import BaseShader, FragmentShader, VertexShader
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
    Using Qt's OpenGL system
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
    def texture_location(self):
        if self._texture_location is None:
            self._texture_location = self.program.uniformLocation("texture_sampler")
            if self._texture_location == -1:
                raise ValueError("Could not find texture_sampler attribute")
        return self._texture_location

    @property
    def tween_location(self) -> int:
        if self._tween_location is None:
            self._tween_location = self.program.uniformLocation("tween")
            if self._tween_location == -1:
                raise ValueError("Could not find attribute")
        return self._tween_location

    @property
    def model_view_projection_matrix_location(self) -> int:
        if self._model_view_projection_matrix_location is None:
            self._model_view_projection_matrix_location = self.program.uniformLocation("model_view_projection_matrix")
            if self._model_view_projection_matrix_location == -1:
                raise ValueError("Could not find attribute")
        return self._model_view_projection_matrix_location

    def draw(self, model_view_proj_matrix: NDArray[np.floating], texture: int, vertex_array_object: IVAO,
             tween: float):
        """Draws the texture using the vertex and index buffers."""
        try:
            # Check for errors from previous operations before starting draw
            # This will raise if there's an error, helping us find the source
            raise_on_error("at start of texture_shader.draw - checking for prior errors")
            
            # Use the shader program
            self.program.bind()
            raise_on_error("after program.bind() in draw")
            
            # When using raw OpenGL calls (glUniform*), we need to ensure glUseProgram is called
            # PyQt6's bind() might not be sufficient, so call it explicitly
            program_id = self.program.programId()
            if program_id == 0:
                raise RuntimeError("Shader program ID is 0 - program not initialized")
            
            gl.glUseProgram(program_id)
            raise_on_error("after glUseProgram in draw")

            # Validate texture ID before using it
            if texture == 0:
                raise RuntimeError(f"Invalid texture ID: {texture}")
            
            # Set the active texture and bind it
            gl.glActiveTexture(gl.GL_TEXTURE0)
            raise_on_error("after glActiveTexture in draw")
            gl.glBindTexture(gl.GL_TEXTURE_2D, texture)
            raise_on_error("after glBindTexture in draw")
            
            # Verify texture is actually bound (only in debug mode to avoid performance impact)
            if nornir_imageregistration.in_debug_mode():
                bound_texture = gl.glGetIntegerv(gl.GL_TEXTURE_BINDING_2D)
                if bound_texture != texture:
                    raise RuntimeError(f"Failed to bind texture {texture}, currently bound: {bound_texture}")

            # Bind VAO - check return value to ensure it succeeded
            if not vertex_array_object.bind():
                raise RuntimeError("Failed to bind VAO - VAO may be invalid or context error")

            # Set uniform values
            # PyQt6's setUniformValue may have issues with integer locations or string names
            # Use raw OpenGL calls for reliability
            tween_loc = self.tween_location
            if tween_loc == -1:
                raise ValueError("tween uniform not found in shader")
            gl.glUniform1f(tween_loc, tween)
            raise_on_error("after glUniform1f(tween) in draw")
            
            texture_loc = self.texture_location
            if texture_loc == -1:
                raise ValueError("texture_sampler uniform not found in shader")
            gl.glUniform1i(texture_loc, 0)
            raise_on_error("after glUniform1i(texture) in draw")

            # Set the model-view-projection matrix
            # Use PyQt6's setUniformValue with QMatrix4x4 - this is more reliable than raw OpenGL
            # QMatrix4x4 expects data in column-major order (OpenGL standard)
            # Numpy arrays are row-major, so we need to transpose
            matrix_transposed = model_view_proj_matrix.astype(np.float32).T
            # QMatrix4x4 constructor can take 16 float values
            matrix_list = matrix_transposed.flatten().tolist()
            matrix_4x4 = QMatrix4x4(*matrix_list)
            
            # Use PyQt6's setUniformValue which handles the binding internally
            self.program.setUniformValue(self.model_view_projection_matrix_location, matrix_4x4)
            raise_on_error("after setUniformValue(matrix) in draw")
            
            # Note: We don't need to re-bind the program or VAO - setUniformValue doesn't affect program/VAO state
            # The program remains active from program.bind() and glUseProgram() calls above
            # The VAO remains bound from the initial bind() call above

            if vertex_array_object.num_elements == 0:
                warnings.warn("No elements to draw")
                return

            gl.glDrawElements(gl.GL_TRIANGLES, vertex_array_object.num_elements, gl.GL_UNSIGNED_SHORT, None)
            raise_on_error("after glDrawElements in draw")
        finally:
                # Check for errors in finally block - but don't raise, just log
                # This is cleanup, so we want to see errors but not fail on them 
                raise_on_error("in texture_shader.draw finally block")
                vertex_array_object.unbind()
                raise_on_error("after VAO unbind in draw")
                self.program.release()
                raise_on_error("after program.release() in draw")
