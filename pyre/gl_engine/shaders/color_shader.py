from OpenGL import GL as gl
from OpenGL.GL import shaders as glshaders
import numpy as np
from numpy._typing import NDArray

from pyre.gl_engine.shaders import BaseShader, FragmentShader, VertexShader
from pyre.gl_engine import check_for_error
from pyre.gl_engine.shader_vao import ShaderVAO
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

        if self._vertex_shader is None:
            self._vertex_shader = VertexShader(_color_vertex_shader_program)

        if self._fragment_shader is None:
            self._fragment_shader = FragmentShader(_color_fragment_shader_program)

        if self._program is None:
            self._program = glshaders.compileProgram(
                self._vertex_shader.shader, self._fragment_shader.shader)

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
    def tween_location(self) -> int:
        if self._tween_location is None:
            self._tween_location = gl.glGetUniformLocation(self.program, "tween")
            if self._tween_location == -1:
                raise ValueError("Could not find attribute")
        return self._tween_location

    @property
    def model_view_projection_matrix(self) -> int:
        if self._model_view_projection_matrix_location is None:
            self._model_view_projection_matrix_location = gl.glGetUniformLocation(self.program,
                                                                                  "model_view_projection_matrix")
            if self._model_view_projection_matrix_location == -1:
                raise ValueError("Could not find attribute")
        return self._model_view_projection_matrix_location

    def draw(self, model_view_proj_matrix: NDArray[np.floating], vertex_array_object: ShaderVAO, tween: float):
        """Draws the texture using the vertex and index buffers."""
        try:
            gl.glUseProgram(self.program)
            check_for_error()
            vertex_array_object.bind()

            gl.glUniform1f(self.tween_location, tween)
            check_for_error()

            gl.glUniformMatrix4fv(self.model_view_projection_matrix, 1, False,
                                  model_view_proj_matrix.astype(np.float32))
            check_for_error()

            status = gl.glCheckFramebufferStatus(gl.GL_FRAMEBUFFER)
            if status != gl.GL_FRAMEBUFFER_COMPLETE:
                print("Framebuffer is not complete")

            gl.glDrawElements(gl.GL_TRIANGLES, vertex_array_object.num_elements, gl.GL_UNSIGNED_SHORT, None)
        finally:
            check_for_error()
            vertex_array_object.unbind()
            gl.glUseProgram(0)
