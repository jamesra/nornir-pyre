import ctypes
from collections.abc import Sequence

from OpenGL import GL as gl
import numpy as np
from numpy._typing import NDArray

from pyre.gl_engine import check_for_error
from pyre.gl_engine.shader_vao import ShaderVAO
from pyre.gl_engine.shaders.shader_base import BaseShader, FragmentShader, VertexShader
from pyre.gl_engine.vertex_attribute import VertexAttribute
from pyre.gl_engine.vertexarraylayout import VertexArrayLayout

_DEFAULT_COLOR = np.array((0.5, 1.0, 0.0, 0.5), dtype=np.float32)

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
    uniform vec4 color;
    layout(location = 0) out vec4 outputColor;
    out float gl_FragDepth;
    void main() {
        outputColor = color;
        gl_FragDepth = 0;
    }
"""


class ColorShader(BaseShader):
    """Solid-color geometry (source/target tween), including registration cell overlays."""

    _source_pos_location: int | None = None
    _target_pos_location: int | None = None
    _tween_location: int | None = None
    _color_location: int | None = None
    _model_view_projection_matrix_location: int | None = None

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
            self._source_pos_location = gl.glGetAttribLocation(self.program, "vertex_source_position")
            if self._source_pos_location == -1:
                raise ValueError("Could not find attribute")
        assert self._source_pos_location is not None
        return self._source_pos_location

    @property
    def target_pos_location(self) -> int:
        if self._target_pos_location is None:
            self._target_pos_location = gl.glGetAttribLocation(self.program, "vertex_target_position")
            if self._target_pos_location == -1:
                raise ValueError("Could not find attribute")
        assert self._target_pos_location is not None
        return self._target_pos_location

    @property
    def tween_location(self) -> int:
        if self._tween_location is None:
            self._tween_location = gl.glGetUniformLocation(self.program, "tween")
            if self._tween_location == -1:
                raise ValueError("Could not find attribute")
        assert self._tween_location is not None
        return self._tween_location

    @property
    def color_location(self) -> int:
        if self._color_location is None:
            self._color_location = gl.glGetUniformLocation(self.program, "color")
            if self._color_location == -1:
                raise ValueError("Could not find attribute")
        assert self._color_location is not None
        return self._color_location

    @property
    def model_view_projection_matrix(self) -> int:
        if self._model_view_projection_matrix_location is None:
            self._model_view_projection_matrix_location = gl.glGetUniformLocation(self.program,
                                                                                  "model_view_projection_matrix")
            if self._model_view_projection_matrix_location == -1:
                raise ValueError("Could not find attribute")
        assert self._model_view_projection_matrix_location is not None
        return self._model_view_projection_matrix_location

    def draw(self,
             model_view_proj_matrix: NDArray[np.floating],
             vertex_array_object: ShaderVAO,
             tween: float,
             color: Sequence[float] | NDArray[np.floating] | None = None,
             mode: int = gl.GL_TRIANGLES):
        """Draw indexed geometry with a constant RGBA color."""
        rgba = _DEFAULT_COLOR if color is None else np.asarray(color, dtype=np.float32).ravel()[:4]
        try:
            gl.glUseProgram(self.program)
            check_for_error()
            vertex_array_object.bind()

            gl.glUniform1f(self.tween_location, tween)
            check_for_error()
            gl.glUniform4f(self.color_location, float(rgba[0]), float(rgba[1]), float(rgba[2]), float(rgba[3]))
            check_for_error()

            gl.glUniformMatrix4fv(self.model_view_projection_matrix, 1, False,
                                  model_view_proj_matrix.astype(np.float32))
            check_for_error()

            gl.glDrawElements(
                mode,
                vertex_array_object.num_elements,
                gl.GL_UNSIGNED_SHORT,
                ctypes.c_void_p(0),
            )
        finally:
            check_for_error()
            vertex_array_object.unbind()
            gl.glUseProgram(0)
