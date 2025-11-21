from OpenGL import GL as gl
import numpy as np
from numpy._typing import NDArray

from pyre.gl_engine import raise_on_error, check_for_error
from pyre.gl_engine.shader_vao import ShaderVAO
from pyre.gl_engine.shaders_qt.shader_base_qt import BaseShader, FragmentShader, VertexShader
from pyre.gl_engine.vertex_attribute import VertexAttribute
from pyre.gl_engine.vertexarraylayout import VertexArrayLayout

_color_vertex_shader_program = """
        #version 330
        uniform float tween; //The fractional amount of the tween between source and target space
        uniform mat4 model_view_projection_matrix; 
        in vec3 vertex_source_position;
        in vec3 vertex_target_position; 
        void main(){
            gl_Position = model_view_projection_matrix * mix(vec4(vertex_source_position, 1),
                                                             vec4(vertex_target_position, 1),
                                                             tween);
        }
"""
_color_fragment_shader_program = """
    #version 330  
    layout(location = 0) out vec4 outputColor;
    out float gl_FragDepth;
    void main() {
        outputColor = vec4(0.5f, 1.0f, 0.0f, 0.5f);
        gl_FragDepth = 0;
    }
"""


class ColorShader(BaseShader):
    """
    Colors fragments with a constant color, used for testing
    Using Qt's OpenGL system
    """

    _source_pos_location = None
    _target_pos_location = None
    _tween_location = None
    _model_view_projection_matrix_location = None

    def __init__(self):
        """initialize the static class.  This must be called AFTER the OpenGL context is created."""
        global _color_vertex_shader_program
        global _color_fragment_shader_program

        self._vertex_layout = VertexArrayLayout(
            [VertexAttribute(lambda: self.source_pos_location, "vertex_source_position", 3, gl.GL_FLOAT),
             VertexAttribute(lambda: self.target_pos_location, "vertex_target_position", 3, gl.GL_FLOAT)])

        self._vertex_shader = VertexShader(_color_vertex_shader_program)
        self._fragment_shader = FragmentShader(_color_fragment_shader_program)

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
    def tween_location(self) -> int:
        if self._tween_location is None:
            self._tween_location = self.program.uniformLocation("tween")
            if self._tween_location == -1:
                raise ValueError("Could not find attribute")
        return self._tween_location

    @property
    def model_view_projection_matrix(self) -> int:
        if self._model_view_projection_matrix_location is None:
            self._model_view_projection_matrix_location = self.program.uniformLocation("model_view_projection_matrix")
            if self._model_view_projection_matrix_location == -1:
                raise ValueError("Could not find attribute")
        return self._model_view_projection_matrix_location

    def draw(self, model_view_proj_matrix: NDArray[np.floating], vertex_array_object: ShaderVAO, tween: float):
        """Draws the texture using the vertex and index buffers."""
        try:
            # Check for errors from previous operations before starting draw
            raise_on_error("at start of color_shader.draw")
            
            # Use the shader program
            self.program.bind()
            raise_on_error("after program.bind() in draw")
            
            # When using raw OpenGL calls (glUniform*), we need to ensure glUseProgram is called
            program_id = self.program.programId()
            gl.glUseProgram(program_id)
            raise_on_error("after glUseProgram in draw")
            
            vertex_array_object.bind()

            # Set uniform values
            self.program.setUniformValue(self.tween_location, tween)
            raise_on_error("after setUniformValue(tween) in draw")

            # Set the model-view-projection matrix
            # PyQt6's setUniformValueArray has a different signature, so use raw OpenGL
            location = self.model_view_projection_matrix
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

            status = gl.glCheckFramebufferStatus(gl.GL_FRAMEBUFFER)
            if status != gl.GL_FRAMEBUFFER_COMPLETE:
                print("Framebuffer is not complete")

            gl.glDrawElements(gl.GL_TRIANGLES, vertex_array_object.num_elements, gl.GL_UNSIGNED_SHORT, None)
            raise_on_error("after glDrawElements in draw")
        finally:
            check_for_error("in draw finally block")
            vertex_array_object.unbind()
            self.program.release()
