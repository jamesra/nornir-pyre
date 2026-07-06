from typing import Sequence

from OpenGL import GL as gl
import numpy as np
from numpy._typing import NDArray

from pyre.gl_engine import IVAO, check_for_error, raise_on_error
from pyre.gl_engine.shaders.shader_base import BaseShader, FragmentShader, VertexShader
from pyre.gl_engine.vertex_attribute import VertexAttribute
from pyre.gl_engine.vertexarraylayout import VertexArrayLayout

_texture_vertex_shader_program = """
        #version 330
        uniform float tween;
        uniform float use_rigid_path;
        uniform float rigid_native_is_warped;
        uniform float rigid_fixed_warped_into_target;
        uniform mat3 rigid_source_to_target;
        uniform mat3 rigid_target_to_source;
        uniform vec2 rigid_interactive_native_shift;
        uniform mat3 rigid_warped_display_matrix;
        uniform mat3 rigid_fixed_display_matrix;
        uniform mat4 model_view_projection_matrix;
        out vec2 frag_texture_coordinate;
        in vec3 vertex_source_position;
        in vec3 vertex_target_position;
        in vec2 vertex_texture_coordinate;
        void main(){
            vec3 native_pos = vertex_source_position;
            vec3 warped_pos = native_pos;
            vec3 fixed_pos = native_pos;
            if (use_rigid_path > 0.5) {
                vec3 yx_in = vec3(native_pos.y, native_pos.x, 1.0);
                fixed_pos = native_pos;
                if (rigid_native_is_warped > 0.5) {
                    // Target image tiles: corners are already in fixed/target space.
                    warped_pos = native_pos;
                } else {
                    // Source/mapped image tiles: warped slot maps native corners through forward.
                    vec3 yx_out = rigid_source_to_target * yx_in;
                    warped_pos = vec3(yx_out.y, yx_out.x, native_pos.z);
                }
            } else {
                warped_pos = vertex_source_position;
                fixed_pos = vertex_target_position;
            }
            if (use_rigid_path > 0.5 && rigid_fixed_warped_into_target > 0.5 && rigid_native_is_warped < 0.5) {
                // Composite source FBO: fixed image drawn at tween=1 must use transformed
                // positions (old mesh target slot), not native fixed corners.
                fixed_pos = warped_pos;
                if (length(rigid_interactive_native_shift) > 0.001) {
                    vec3 shift = vec3(rigid_interactive_native_shift.y,
                                      rigid_interactive_native_shift.x, 0.0);
                    fixed_pos += shift;
                    warped_pos = fixed_pos;
                }
            }
            if (length(rigid_interactive_native_shift) > 0.001) {
                // Uniform is (delta_y, delta_x); native_pos.x is image X, native_pos.y is image Y.
                vec3 shift = vec3(rigid_interactive_native_shift.y,
                                  rigid_interactive_native_shift.x, 0.0);
                if (rigid_native_is_warped > 0.5) {
                    warped_pos += shift;
                } else if (rigid_fixed_warped_into_target < 0.5) {
                    fixed_pos += shift;
                }
            }
            if (use_rigid_path > 0.5 && rigid_native_is_warped > 0.5) {
                vec3 yx_in = vec3(warped_pos.y, warped_pos.x, 1.0);
                vec3 yx_out = rigid_warped_display_matrix * yx_in;
                warped_pos = vec3(yx_out.y, yx_out.x, warped_pos.z);
            }
            if (use_rigid_path > 0.5 && rigid_native_is_warped < 0.5 && rigid_fixed_warped_into_target > 0.5) {
                vec3 yx_in = vec3(fixed_pos.y, fixed_pos.x, 1.0);
                vec3 yx_out = rigid_fixed_display_matrix * yx_in;
                fixed_pos = vec3(yx_out.y, yx_out.x, fixed_pos.z);
                warped_pos = fixed_pos;
            }
            gl_Position = model_view_projection_matrix * mix(vec4(fixed_pos, 1),
                                                             vec4(warped_pos, 1),
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
    _use_rigid_path_location = None
    _rigid_native_is_warped_location = None
    _rigid_fixed_warped_into_target_location = None
    _rigid_matrix_location = None
    _rigid_inverse_matrix_location = None
    _rigid_interactive_native_shift_location = None
    _rigid_warped_display_matrix_location = None
    _rigid_fixed_display_matrix_location = None
    _attributes: Sequence[VertexAttribute] | None = None

    def __init__(self):
        """initialize the static class.  This must be called AFTER the OpenGL context is created."""
        global _texture_vertex_shader_program
        global _texture_fragment_shader_program


        self._vertex_shader = VertexShader(_texture_vertex_shader_program)
        self._fragment_shader = FragmentShader(_texture_fragment_shader_program)
        
        self._vertex_layout = VertexArrayLayout(
            [VertexAttribute(lambda: self.target_pos_location, "vertex_target_position", 3, gl.GL_FLOAT),
             VertexAttribute(lambda: self.source_pos_location, "vertex_source_position", 3, gl.GL_FLOAT),
             VertexAttribute(lambda: self.texture_coord_location, "vertex_texture_coordinate", 2, gl.GL_FLOAT)])

    def initialize_gl_objects(self):
        super().initialize_gl_objects()

    @property
    def source_pos_location(self) -> int:
        if self._source_pos_location is None:
            self._source_pos_location = gl.glGetAttribLocation(self.program, "vertex_source_position")
            raise_on_error("after glGetAttribLocation(vertex_source_position) in texture_shader")
            if self._source_pos_location == -1:
                raise ValueError("Could not find attribute")
        return self._source_pos_location

    @property
    def target_pos_location(self) -> int:
        if self._target_pos_location is None:
            self._target_pos_location = gl.glGetAttribLocation(self.program, "vertex_target_position")
            raise_on_error("after glGetAttribLocation(vertex_target_position) in texture_shader")
            if self._target_pos_location == -1:
                raise ValueError("Could not find attribute")
        return self._target_pos_location

    @property
    def texture_coord_location(self) -> int:
        if self._texture_coord_location is None:
            self._texture_coord_location = gl.glGetAttribLocation(self.program, "vertex_texture_coordinate")
            raise_on_error("after glGetAttribLocation(texture_coord_location) in texture_shader")
            if self._texture_coord_location == -1:
                raise ValueError("Could not find texture coordinate attribute")
        return self._texture_coord_location

    @property
    def texture_location(self):
        if self._texture_location is None:
            self._texture_location = gl.glGetUniformLocation(self.program, "texture_sampler")
            raise_on_error("after glGetUniformLocation(texture_sampler) in texture_shader")  
            if self._texture_location == -1:
                raise ValueError("Could not find texture_sampler attribute")
        return self._texture_location

    @property
    def tween_location(self) -> int:
        if self._tween_location is None:
            self._tween_location = gl.glGetUniformLocation(self.program, "tween")
            raise_on_error("after glGetUniformLocation(tween) in texture_shader")
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

    @property
    def use_rigid_path_location(self) -> int:
        if self._use_rigid_path_location is None:
            self._use_rigid_path_location = gl.glGetUniformLocation(self.program, "use_rigid_path")
            raise_on_error("after glGetUniformLocation(use_rigid_path) in texture_shader")
        return self._use_rigid_path_location

    @property
    def rigid_matrix_location(self) -> int:
        if self._rigid_matrix_location is None:
            self._rigid_matrix_location = gl.glGetUniformLocation(self.program, "rigid_source_to_target")
            raise_on_error("after glGetUniformLocation(rigid_source_to_target) in texture_shader")
        return self._rigid_matrix_location

    @property
    def rigid_fixed_warped_into_target_location(self) -> int:
        if self._rigid_fixed_warped_into_target_location is None:
            self._rigid_fixed_warped_into_target_location = gl.glGetUniformLocation(
                self.program, "rigid_fixed_warped_into_target")
            raise_on_error("after glGetUniformLocation(rigid_fixed_warped_into_target) in texture_shader")
        return self._rigid_fixed_warped_into_target_location

    @property
    def rigid_native_is_warped_location(self) -> int:
        if self._rigid_native_is_warped_location is None:
            self._rigid_native_is_warped_location = gl.glGetUniformLocation(self.program, "rigid_native_is_warped")
            raise_on_error("after glGetUniformLocation(rigid_native_is_warped) in texture_shader")
        return self._rigid_native_is_warped_location

    @property
    def rigid_inverse_matrix_location(self) -> int:
        if self._rigid_inverse_matrix_location is None:
            self._rigid_inverse_matrix_location = gl.glGetUniformLocation(self.program, "rigid_target_to_source")
            raise_on_error("after glGetUniformLocation(rigid_target_to_source) in texture_shader")
        return self._rigid_inverse_matrix_location

    @property
    def rigid_interactive_native_shift_location(self) -> int:
        if self._rigid_interactive_native_shift_location is None:
            self._rigid_interactive_native_shift_location = gl.glGetUniformLocation(
                self.program, "rigid_interactive_native_shift")
            raise_on_error("after glGetUniformLocation(rigid_interactive_native_shift) in texture_shader")
        return self._rigid_interactive_native_shift_location

    @property
    def rigid_warped_display_matrix_location(self) -> int:
        if self._rigid_warped_display_matrix_location is None:
            self._rigid_warped_display_matrix_location = gl.glGetUniformLocation(
                self.program, "rigid_warped_display_matrix")
            raise_on_error("after glGetUniformLocation(rigid_warped_display_matrix) in texture_shader")
        return self._rigid_warped_display_matrix_location

    @property
    def rigid_fixed_display_matrix_location(self) -> int:
        if self._rigid_fixed_display_matrix_location is None:
            self._rigid_fixed_display_matrix_location = gl.glGetUniformLocation(
                self.program, "rigid_fixed_display_matrix")
            raise_on_error("after glGetUniformLocation(rigid_fixed_display_matrix) in texture_shader")
        return self._rigid_fixed_display_matrix_location

    @staticmethod
    def _as_numpy_mat3(matrix) -> NDArray[np.floating]:
        mat = matrix.get() if hasattr(matrix, 'get') else np.asarray(matrix)
        return np.asarray(mat, dtype=np.float32).reshape(3, 3)

    @staticmethod
    def rigid_matrices_from_transform(transform) -> tuple[NDArray[np.floating], NDArray[np.floating]]:
        """Return (forward, inverse) 3x3 row-major matrices in Nornir (Y,X) homogeneous form."""
        forward = np.eye(3, dtype=np.float32)
        inverse = np.eye(3, dtype=np.float32)
        fwd = getattr(transform, 'forward_matrix', None)
        inv = getattr(transform, 'inverse_matrix', None)
        if fwd is not None:
            forward = TextureShader._as_numpy_mat3(fwd)
        if inv is not None:
            inverse = TextureShader._as_numpy_mat3(inv)
        return forward, inverse

    @staticmethod
    def rigid_matrix_from_transform(transform) -> NDArray[np.floating]:
        """Build 3x3 row-major matrix mapping source (X,Y,1) to target (X,Y) for rigid transforms."""
        return TextureShader.rigid_matrices_from_transform(transform)[0]

    def draw(self, model_view_proj_matrix: NDArray[np.floating], texture: int, vertex_array_object: IVAO,
             tween: float, use_rigid_path: bool = False,
             rigid_source_to_target: NDArray[np.floating] | None = None,
             rigid_target_to_source: NDArray[np.floating] | None = None,
             rigid_native_is_warped: bool = False,
             rigid_fixed_warped_into_target: bool = False,
             rigid_interactive_native_shift: NDArray[np.floating] | None = None,
             rigid_warped_display_matrix: NDArray[np.floating] | None = None,
             rigid_fixed_display_matrix: NDArray[np.floating] | None = None):
        """Draws the texture using the vertex and index buffers."""
        try:
            gl.glUseProgram(self.program)
            check_for_error()

            gl.glActiveTexture(gl.GL_TEXTURE0)
            check_for_error()
            gl.glBindTexture(gl.GL_TEXTURE_2D, texture)
            check_for_error()

            vertex_array_object.bind()

            gl.glUniform1f(self.tween_location, float(tween))
            check_for_error()
            gl.glUniform1f(self.use_rigid_path_location, 1.0 if use_rigid_path else 0.0)
            check_for_error()
            gl.glUniform1f(self.rigid_native_is_warped_location, 1.0 if rigid_native_is_warped else 0.0)
            check_for_error()
            gl.glUniform1f(self.rigid_fixed_warped_into_target_location,
                            1.0 if rigid_fixed_warped_into_target else 0.0)
            check_for_error()
            if rigid_source_to_target is None:
                rigid_source_to_target = np.eye(3, dtype=np.float32)
            if rigid_target_to_source is None:
                rigid_target_to_source = np.eye(3, dtype=np.float32)
            gl.glUniformMatrix3fv(self.rigid_matrix_location, 1, True,
                                  rigid_source_to_target.astype(np.float32, copy=False))
            check_for_error()
            gl.glUniformMatrix3fv(self.rigid_inverse_matrix_location, 1, True,
                                  rigid_target_to_source.astype(np.float32, copy=False))
            check_for_error()
            if rigid_interactive_native_shift is None:
                rigid_interactive_native_shift = np.zeros(2, dtype=np.float32)
            gl.glUniform2fv(self.rigid_interactive_native_shift_location, 1,
                            rigid_interactive_native_shift.astype(np.float32, copy=False))
            check_for_error()
            if rigid_warped_display_matrix is None:
                rigid_warped_display_matrix = np.eye(3, dtype=np.float32)
            gl.glUniformMatrix3fv(self.rigid_warped_display_matrix_location, 1, True,
                                  rigid_warped_display_matrix.astype(np.float32, copy=False))
            check_for_error()
            if rigid_fixed_display_matrix is None:
                rigid_fixed_display_matrix = np.eye(3, dtype=np.float32)
            gl.glUniformMatrix3fv(self.rigid_fixed_display_matrix_location, 1, True,
                                  rigid_fixed_display_matrix.astype(np.float32, copy=False))
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
                return

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
