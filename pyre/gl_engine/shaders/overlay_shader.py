"""
Displays two textures and overlays them with a blend function
"""
import ctypes
from enum import Enum
from typing import Sequence
import warnings

from OpenGL import GL as gl
from OpenGL.GL import shaders as glshaders
import numpy as np
from numpy._typing import NDArray
from PyQt6.QtGui import QOpenGLContext

from pyre.gl_engine import raise_on_error
from pyre.gl_engine.shader_vao import ShaderVAO
from pyre.gl_engine.shaders.shader_base import BaseShader, FragmentShader, VertexShader, bind_texture
from pyre.gl_engine.vertex_attribute import VertexAttribute
from pyre.gl_engine.vertexarraylayout import VertexArrayLayout
from pyre.gl_engine.overlaytype import OverlayType

# Define vertices for a full-screen quad
full_screen_vertices = np.array([
    -1.0, -1.0, 0.0, 0.0, 0.0,  # Bottom-left corner
    1.0, -1.0, 0.0, 1.0, 0.0,  # Bottom-right corner
    1.0, 1.0, 0.0, 1.0, 1.0,  # Top-right corner
    -1.0, 1.0, 0.0, 0.0, 1.0  # Top-left corner
], dtype=np.float32)

# Define indices for the quad (two triangles); must match glDrawElements(GL_UNSIGNED_SHORT)
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
    This is a shader that has a pair of vertices and textures for source/target space and can tween between them.
    Program is compiled per OpenGL context so the composite window (separate context) can render.
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

    _vao: ShaderVAO | None  # Vertex array object for this shader.  All shaders can share vertices since we simply copy two textures directly to the back buffer.

    # Per-context program so composite (and other windows) each have a valid program in their context.
    _context_programs: dict[QOpenGLContext, int]
    _last_context_used: QOpenGLContext | None = None

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
        self._context_programs = {}

    def _clear_location_caches(self) -> None:
        """Clear cached uniform/attribute locations when switching context."""
        self._vertex_position_location = None
        self._texture_coord_location = None
        self._source_texture_location = None
        self._target_texture_location = None
        self._model_view_projection_matrix_location = None
        self._source_channel_blend_location = None
        self._target_channel_blend_location = None

    def initialize_gl_objects(self):
        context = QOpenGLContext.currentContext()
        if not context or not context.isValid():
            return
        if context in self._context_programs:
            if self._vao is None:
                self._vao = self.create_vao()
            return
        # Compile and link program for this context (required for composite window's separate context).
        vsh = glshaders.compileShader(_overlay_vertex_shader_program, gl.GL_VERTEX_SHADER)
        fsh = glshaders.compileShader(_overlay_channel_mix_texture_fragment_shader_program, gl.GL_FRAGMENT_SHADER)
        prog = glshaders.compileProgram(vsh, fsh)
        gl.glDeleteShader(vsh)
        gl.glDeleteShader(fsh)
        self._context_programs[context] = int(prog)
        if self._vao is None:
            self._vao = self.create_vao()

    def initialized(self) -> bool:
        """True if the overlay has a program for the current context."""
        context = QOpenGLContext.currentContext()
        return context is not None and context.isValid() and context in self._context_programs

    @property
    def program(self) -> int:
        """Program for the current OpenGL context (compiled per-context)."""
        context = QOpenGLContext.currentContext()
        if not context or not context.isValid():
            raise ValueError("No valid OpenGL context current")
        if context not in self._context_programs:
            self.initialize_gl_objects()
        if context not in self._context_programs:
            raise ValueError("Shaders have not been initialized for this context")
        if self._last_context_used is not context:
            self._clear_location_caches()
            self._last_context_used = context
        return self._context_programs[context]

    @property
    def vertex_position_location(self) -> int:
        if self._vertex_position_location is None:
            self._vertex_position_location = gl.glGetAttribLocation(self.program, "vertex_position")
            if self._vertex_position_location == -1:
                raise ValueError("Could not find attribute")
        assert self._vertex_position_location is not None
        return self._vertex_position_location

    @property
    def texture_coord_location(self) -> int:
        if self._texture_coord_location is None:
            self._texture_coord_location = gl.glGetAttribLocation(self.program, "vertex_texture_coordinate")
            if self._texture_coord_location == -1:
                raise ValueError("Could not find texture coordinate attribute")
        assert self._texture_coord_location is not None
        return self._texture_coord_location

    @property
    def source_texture_location(self) -> int:
        if self._source_texture_location is None:
            self._source_texture_location = gl.glGetUniformLocation(self.program, "source_texture")
            if self._source_texture_location == -1:
                raise ValueError("Could not find texture_sampler attribute")
        assert self._source_texture_location is not None
        return self._source_texture_location

    @property
    def target_texture_location(self) -> int:
        if self._target_texture_location is None:
            self._target_texture_location = gl.glGetUniformLocation(self.program, "target_texture")
            if self._target_texture_location == -1:
                raise ValueError("Could not find texture_sampler attribute")
        assert self._target_texture_location is not None
        return self._target_texture_location

    @property
    def model_view_projection_matrix_location(self) -> int:
        if self._model_view_projection_matrix_location is None:
            self._model_view_projection_matrix_location = gl.glGetUniformLocation(self.program,
                                                                                  "model_view_projection_matrix")
            if self._model_view_projection_matrix_location == -1:
                raise ValueError("Could not find attribute")
        assert self._model_view_projection_matrix_location is not None
        return self._model_view_projection_matrix_location

    @property
    def source_channel_blend_location(self) -> int:
        if self._source_channel_blend_location is None:
            self._source_channel_blend_location = gl.glGetUniformLocation(self.program,
                                                                          "source_channel_blend")
            if self._source_channel_blend_location == -1:
                raise ValueError("Could not find attribute")
        assert self._source_channel_blend_location is not None
        return self._source_channel_blend_location

    @property
    def target_channel_blend_location(self) -> int:
        if self._target_channel_blend_location is None:
            self._target_channel_blend_location = gl.glGetUniformLocation(self.program,
                                                                          "target_channel_blend")
            if self._target_channel_blend_location == -1:
                raise ValueError("Could not find attribute")
        assert self._target_channel_blend_location is not None
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
        :param vertex_array_object: The vertex array object with vertices defined for source and target space vertices and texture coordinates
        :param vertex_tween: The fractional amount of the tween between source and target space for vertices
        :param texture_tween: The fractional amount of the tween between source and target textures
        """
        if self._vao is None:
            raise ValueError("Overlay shader VAO is not initialized")
        
        bound_vao = False
        try:
            # if overlay_type is None:
            gl.glUseProgram(self.program)
            # else:
            #     gl.glUseProgram(self._programs[overlay_type])

            raise_on_error("after glUseProgram in draw")
            bound_vao = self._vao.bind()

            src_loc = self.source_texture_location
            tgt_loc = self.target_texture_location
            bind_texture(source_texture, src_loc, gl.GL_TEXTURE0)
            bind_texture(target_texture, tgt_loc, gl.GL_TEXTURE1)

            gl.glUniform4fv(self.source_channel_blend_location, 1, source_channel_mix.astype(np.float32, copy=False))
            raise_on_error("after glUniform4fv(source_channel_blend) in draw")
            gl.glUniform4fv(self.target_channel_blend_location, 1, target_channel_mix.astype(np.float32, copy=False))
            raise_on_error("after glUniform4fv(target_channel_blend) in draw")
            gl.glUniformMatrix4fv(self.model_view_projection_matrix_location, 1, False,
                                  model_view_proj_matrix.astype(np.float32, copy=False))
            raise_on_error("after glUniformMatrix4fv in draw")

            if self._vao.num_elements == 0:
                warnings.warn("No elements to draw")
                
            # Use explicit offset 0 for VAO element buffer (None can cause GL_INVALID_ENUM on some drivers)
            gl.glDrawElements(gl.GL_TRIANGLES, self._vao.num_elements, gl.GL_UNSIGNED_SHORT, ctypes.c_void_p(0))
            raise_on_error("after glDrawElements in draw")
        finally:
            raise_on_error("in draw finally block")
            if bound_vao:
                self._vao.unbind()
                raise_on_error("after unbind in draw finally block")
            gl.glUseProgram(0)
            raise_on_error("after glUseProgram(0) in draw finally block")
