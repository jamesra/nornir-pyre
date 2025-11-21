"""
Displays two textures and overlays them with a blend function
Using Qt's OpenGL system
"""
from enum import Enum
from typing import Sequence
import warnings

from OpenGL import GL as gl
import numpy as np
from numpy._typing import NDArray
from PyQt6.QtGui import QMatrix4x4, QOpenGLContext

from pyre.gl_engine import raise_on_error, check_for_error
from pyre.gl_engine.shader_vao import ShaderVAO
from pyre.gl_engine.shaders_qt.shader_base_qt import BaseShader, FragmentShader, VertexShader, bind_texture
from pyre.gl_engine.overlaytype import OverlayType
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
# Use uint16 to match GL_UNSIGNED_SHORT in glDrawElements
full_screen_indices = np.array([
    0, 1, 2,  # First triangle
    2, 3, 0  # Second triangle
], dtype=np.uint16)

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


class OverlayShader(BaseShader):
    """
    This is a shader that has a pair of verticies and textures for source/target space and can tween between them
    Using Qt's OpenGL system
    """

    _source_texture_location: int | None = None
    _target_texture_location: int | None = None

    _source_channel_blend_location: int | None = None
    _target_channel_blend_location: int | None = None

    _vertex_position_location = None
    _texture_coord_location = None
    _model_view_projection_matrix_location = None
    _attributes: Sequence[VertexAttribute] | None = None

    _fragment_shaders: dict[OverlayType, int]
    _programs: dict[OverlayType, int]  # lookup a program to use based on overlay type

    _vao: ShaderVAO | None  # Vertex array object for this shader.  All shaders can share verticies since we simply copy two textures directly to the back buffer.
    _vao_context: QOpenGLContext | None = None  # The context where the VAO was created

    def __init__(self):
        """initialize the static class.  This must be called AFTER the OpenGL context is created."""
        self._vertex_layout = VertexArrayLayout(
            [VertexAttribute(lambda: self.vertex_position_location, "vertex_position", 3, gl.GL_FLOAT),
             VertexAttribute(lambda: self.texture_coord_location, "vertex_texture_coordinate", 2, gl.GL_FLOAT)])

        self._vao = None
        self._vao_context = None
        self._vertex_shader = VertexShader(_overlay_vertex_shader_program)
        self._fragment_shader = FragmentShader(_overlay_channel_mix_texture_fragment_shader_program)

    def initialize_gl_objects(self):
        super().initialize_gl_objects()

        # for overlay_type, fragment_shader in self._fragment_shaders.items():
        #    self._programs[overlay_type] = glshaders.compileProgram(self._vertex_shader.shader, fragment_shader)

        # Create our vertex array object if it is not initialized
        if self._vao is None:
            # Track the context where the VAO is created
            current_context = QOpenGLContext.currentContext()
            if current_context is None:
                raise RuntimeError("No current OpenGL context when creating VAO in initialize_gl_objects")
            if not current_context.isValid():
                raise RuntimeError("Current OpenGL context is invalid when creating VAO in initialize_gl_objects")

            self._vao = self.create_vao()
            self._vao_context = current_context
            raise_on_error("after VAO creation in initialize_gl_objects")

    @property
    def vertex_position_location(self) -> int:
        if self._vertex_position_location is None:
            self._vertex_position_location = self.program.attributeLocation("vertex_position")
            if self._vertex_position_location == -1:
                raise ValueError("Could not find attribute")
        return self._vertex_position_location

    @property
    def texture_coord_location(self) -> int:
        if self._texture_coord_location is None:
            self._texture_coord_location = self.program.attributeLocation("vertex_texture_coordinate")
            if self._texture_coord_location == -1:
                raise ValueError("Could not find texture coordinate attribute")
        return self._texture_coord_location

    @property
    def source_texture_location(self) -> int:
        if self._source_texture_location is None:
            location = self.program.uniformLocation("source_texture")
            if location == -1:
                raise ValueError("Could not find texture_sampler attribute")
            self._source_texture_location = location
        assert self._source_texture_location is not None
        return self._source_texture_location

    @property
    def target_texture_location(self) -> int:
        if self._target_texture_location is None:
            location = self.program.uniformLocation("target_texture")
            if location == -1:
                raise ValueError("Could not find texture_sampler attribute")
            self._target_texture_location = location
        assert self._target_texture_location is not None
        return self._target_texture_location

    @property
    def model_view_projection_matrix_location(self) -> int:
        if self._model_view_projection_matrix_location is None:
            self._model_view_projection_matrix_location = self.program.uniformLocation("model_view_projection_matrix")
            if self._model_view_projection_matrix_location == -1:
                raise ValueError("Could not find attribute")
        return self._model_view_projection_matrix_location

    @property
    def source_channel_blend_location(self) -> int:
        if self._source_channel_blend_location is None:
            location = self.program.uniformLocation("source_channel_blend")
            if location == -1:
                raise ValueError("Could not find attribute")
            self._source_channel_blend_location = location
        assert self._source_channel_blend_location is not None
        return self._source_channel_blend_location

    @property
    def target_channel_blend_location(self) -> int:
        if self._target_channel_blend_location is None:
            location = self.program.uniformLocation("target_channel_blend")
            if location == -1:
                raise ValueError("Could not find attribute")
            self._target_channel_blend_location = location
        assert self._target_channel_blend_location is not None
        return self._target_channel_blend_location

    def create_vao(self) -> ShaderVAO:
        """
        Creates a VertexArrayObject for the overlay shader.
        """
        return ShaderVAO(self._vertex_layout,
                         full_screen_vertices,
                         full_screen_indices)

    def _validate_context(self) -> bool:
        """Validate that the current OpenGL context is valid and ready for rendering.
        Also verifies that context sharing is working if the VAO was created in a different context.
        
        Returns:
            True if context is valid and ready, False otherwise
        """
        # Check if there's a current context
        current_context = QOpenGLContext.currentContext()
        if current_context is None:
            return False

        # Check if context is valid
        if not current_context.isValid():
            return False

        # If VAO was created in a specific context, verify context sharing
        if self._vao_context is not None:
            # Check if contexts share resources (they should be sharing via SharedContext)
            # If they're the same context, that's fine
            if current_context == self._vao_context:
                return True

            # Check if they share a common context (verify sharing is set up)
            share_context = current_context.shareContext()
            vao_share_context = self._vao_context.shareContext()

            # They should share the same shared context, or the current context's share context
            # should match the VAO context's share context
            if share_context is not None and vao_share_context is not None:
                if share_context == vao_share_context:
                    return True

            # As a fallback, try to verify the context is functional with a simple query
            try:
                version = gl.glGetString(gl.GL_VERSION)
                if version is None:
                    return False
            except Exception:
                return False

        return True

    def _set_vec4_uniform(self, location: int, data: NDArray[np.floating], name: str):
        """Helper method to set a vec4 uniform value.
        :param location: The uniform location
        :param data: The data array (must have 4 elements)
        :param name: Name for error messages
        """
        vec4_data = np.ascontiguousarray(
            data.astype(np.float32).flatten(),
            dtype=np.float32
        )
        if len(vec4_data) != 4:
            raise ValueError(f"{name} must have 4 elements, got {len(vec4_data)}")
        gl.glUniform4fv(location, 1, vec4_data)
        raise_on_error(f"after glUniform4fv({name}) in draw")

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
        :param source_channel_mix: The source channel mix
        :param target_channel_mix: The target channel mix
        """
        # Solution 3: Validate context before attempting to draw
        if not self._validate_context():
            # Context is not ready or invalid - skip drawing gracefully
            # This can happen when contexts are being created or switching
            warnings.warn("OpenGL context not ready for overlay shader draw - skipping this frame")
            return

        try:
            # Check for any existing OpenGL errors before starting
            check_for_error("before draw() in overlay_shader")

            self.program.bind()
            # Use the shader program
            # if overlay_type is None:
            # self.program.bind()
            # else:
            #    self._programs[overlay_type].bind()
            raise_on_error("after program.bind() in draw")

            # Bind VAO - it should already be created in initialize_gl_objects
            if self._vao is None:
                raise RuntimeError("VAO not initialized. Call initialize_gl_objects() first.")

            # Solution 3: Validate VAO bind with better error handling
            if not self._vao.bind():
                # VAO bind failed - this might mean context sharing isn't working
                # or the context changed. Check for OpenGL errors to get more info.
                error_code = gl.glGetError()
                if error_code != gl.GL_NO_ERROR:
                    # Clear the error and skip drawing this frame
                    warnings.warn(
                        f"VAO bind failed with OpenGL error {error_code} - context may not be ready. Skipping draw.")
                    self.program.release()
                    raise_on_error("after VAO bind failed in draw and releasing program")
                    return
                else:
                    # Bind returned False but no OpenGL error - might be context issue
                    warnings.warn("VAO bind failed (no OpenGL error) - context may not be ready. Skipping draw.")
                    self.program.release()
                    raise_on_error("after VAO bind failed in draw and releasing program")
                    return

            # Solution 2: Verify VAO bind was successful by checking for errors
            error_code = gl.glGetError()
            if error_code != gl.GL_NO_ERROR:
                # Bind seemed to succeed but there's an error - clear it and skip
                check_for_error("after VAO bind in draw - checking for bind errors")
                warnings.warn(f"OpenGL error after VAO bind ({error_code}) - skipping draw")
                self._vao.unbind()
                self.program.release()
                return

            raise_on_error("after VAO bind in draw")

            # Bind textures
            bind_texture(source_texture, self.source_texture_location, gl.GL_TEXTURE0)
            bind_texture(target_texture, self.target_texture_location, gl.GL_TEXTURE1)

            # Set uniform values
            self._set_vec4_uniform(self.source_channel_blend_location, source_channel_mix, "source_channel_mix")
            self._set_vec4_uniform(self.target_channel_blend_location, target_channel_mix, "target_channel_mix")

            # Set the model-view-projection matrix using QMatrix4x4
            # QMatrix4x4 expects data in column-major order (OpenGL standard)
            # Numpy arrays are row-major, so we need to transpose
            matrix_transposed = model_view_proj_matrix.astype(np.float32).T
            matrix_list = matrix_transposed.flatten().tolist()
            matrix_4x4 = QMatrix4x4(*matrix_list)

            self.program.setUniformValue(self.model_view_projection_matrix_location, matrix_4x4)
            raise_on_error("after setUniformValue(matrix) in draw")

            if self._vao.num_elements == 0:
                warnings.warn("No elements to draw")
                return

            gl.glDrawElements(gl.GL_TRIANGLES, self._vao.num_elements, gl.GL_UNSIGNED_SHORT, None)
            raise_on_error("after glDrawElements in draw")
        finally:
            # Check for errors in finally block - but don't raise, just log
            raise_on_error("in overlay_shader.draw finally block")
            if self._vao is not None:
                self._vao.unbind()
                raise_on_error("after VAO unbind in draw")

            self.program.release()
            raise_on_error("after program.release() in draw")
            # if overlay_type is None:
            # self.program.release()
            # else:
            # self._programs[overlay_type].release()
