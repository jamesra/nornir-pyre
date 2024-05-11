from typing import Sequence

from OpenGL import GL as gl
from OpenGL.GL import shaders as glshaders
import numpy as np
from numpy._typing import NDArray

from pyre.gl_engine import check_for_error
from pyre.gl_engine.shaders.shader_base import FragmentShader, VertexShader, BaseShader
from pyre.gl_engine.shader_vao import ShaderVAO
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

        if self._vertex_shader is None:
            self._vertex_shader = VertexShader(_transform_vertex_shader_program)

        if self._fragment_shader is None:
            self._fragment_shader = FragmentShader(_transform_fragment_shader_program)

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
    def texture_coord_location(self) -> int:
        if self._texture_coord_location is None:
            self._texture_coord_location = gl.glGetAttribLocation(self.program, "vertex_texture_coordinate")
            if self._texture_coord_location == -1:
                raise ValueError("Could not find texture coordinate attribute")
        return self._texture_coord_location

    @property
    def source_texture_location(self):
        if self._source_texture_location is None:
            self._source_texture_location = gl.glGetUniformLocation(self.program, "source_texture")
            if self._source_texture_location == -1:
                raise ValueError("Could not find texture_sampler attribute")
        return self._source_texture_location

    @property
    def target_texture_location(self):
        if self._target_texture_location is None:
            self._target_texture_location = gl.glGetUniformLocation(self.program, "target_texture")
            if self._target_texture_location == -1:
                raise ValueError("Could not find texture_sampler attribute")
        return self._target_texture_location

    @property
    def vertex_tween_location(self) -> int:
        if self._vertex_tween_location is None:
            self._vertex_tween_location = gl.glGetUniformLocation(self.program, "vert_tween")
            if self._vertex_tween_location == -1:
                raise ValueError("Could not find attribute")
        return self._vertex_tween_location

    @property
    def texture_tween_location(self) -> int:
        if self._texture_tween_location is None:
            self._texture_tween_location = gl.glGetUniformLocation(self.program, "texture_tween")
            if self._texture_tween_location == -1:
                raise ValueError("Could not find attribute")
        return self._texture_tween_location

    @property
    def model_view_projection_matrix_location(self) -> int:
        if self._model_view_projection_matrix_location is None:
            self._model_view_projection_matrix_location = gl.glGetUniformLocation(self.program,
                                                                                  "model_view_projection_matrix")
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
            gl.glUseProgram(self.program)
            check_for_error()
            vertex_array_object.bind()

            self.bind_texture(source_texture, self.source_texture_location, gl.GL_TEXTURE0)
            self.bind_texture(target_texture, self.target_texture_location, gl.GL_TEXTURE1)

            # tween = math.floor(time.time() % 2)
            # tween = (time.time() % 15) / 15.0
            gl.glUniform1f(self.vertex_tween_location, vertex_tween)
            check_for_error()
            gl.glUniform1f(self.texture_tween_location, texture_tween)
            check_for_error()
            gl.glUniformMatrix4fv(self.model_view_projection_matrix_location, 1, False,
                                  model_view_proj_matrix.astype(np.float32))
            check_for_error()

            # status = gl.glCheckFramebufferStatus(gl.GL_FRAMEBUFFER)
            # if status != gl.GL_FRAMEBUFFER_COMPLETE:
            #    print("Framebuffer is not complete")

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

    def bind_texture(self, texture: int, texture_location: int, gl_texture: int = gl.GL_TEXTURE0):
        """
        :param gl_texture_number: gl.GL_TEXTURE0, gl.GL_TEXTURE1, etc
        :param texture: Texture resource ID
        :param texture_location: Sampler location ID in the shader
        :return:
        """
        # Set the active texture and bind it
        gl.glActiveTexture(gl.GL_TEXTURE0)
        check_for_error()
        gl.glBindTexture(gl.GL_TEXTURE_2D, texture)
        check_for_error()

        # Assign the sampler to the texture we just bound
        offset = gl_texture - gl.GL_TEXTURE0
        gl.glUniform1i(texture_location, gl.GL_TEXTURE0 + offset)
        check_for_error()
