from abc import abstractmethod, ABC
from OpenGL import GL as gl
from OpenGL.GL import shaders as glshaders
from pyre.gl_engine.vertexarraylayout import VertexArrayLayout
from pyre.gl_engine.helpers import check_for_error


def bind_texture(texture: int, texture_location: int, gl_texture: int = gl.GL_TEXTURE0):
    """
    Bind a texture to the specified texture location in the shader
    :param gl_texture: gl.GL_TEXTURE0, gl.GL_TEXTURE1, etc
    :param texture: Texture resource ID
    :param texture_location: Sampler location ID in the shader
    :return:
    """
    # Set the active texture and bind it
    gl.glActiveTexture(gl_texture)
    check_for_error()
    gl.glBindTexture(gl.GL_TEXTURE_2D, texture)
    check_for_error()

    # Assign the sampler to the texture we just bound
    offset = gl_texture - gl.GL_TEXTURE0
    gl.glUniform1i(texture_location, offset)
    check_for_error()


class VertexShader:
    _shader: int | None = None  # The compiled shader
    _program: str
    _initialized: bool = False  # Whether the shader has been compiled

    @property
    def shader(self) -> int:
        return self._shader

    def __init__(self, vertex_shader_program: str):
        self._program = vertex_shader_program

    def initialize_gl_objects(self):
        if not self._initialized:
            self._shader = glshaders.compileShader(self._program, gl.GL_VERTEX_SHADER)
            self._initialized = True

    def __del__(self):
        if self._shader is not None:
            gl.glDeleteShader(self._shader)


class FragmentShader:
    _shader: int | None = None  # The compiled shader
    _program: str
    _initialized: bool = False  # Whether the shader has been compiled

    @property
    def shader(self) -> int:
        return self._shader

    def __init__(self, vertex_shader_program: str):
        self._program = vertex_shader_program

    def initialize_gl_objects(self):
        if not self._initialized:
            self._shader = glshaders.compileShader(self._program, gl.GL_FRAGMENT_SHADER)
            self._initialized = True

    def __del__(self):
        if self._shader is not None:
            gl.glDeleteShader(self._shader)


class BaseShader(ABC):
    """Shared code for shaders."""
    _vertex_shader: VertexShader
    _fragment_shader: FragmentShader
    _program: int | None = None

    _vertex_layout: VertexArrayLayout

    def initialize_gl_objects(self):
        """Compile the shaders and programs.  Override for different behavior"""
        self._vertex_shader.initialize_gl_objects()
        self._fragment_shader.initialize_gl_objects()

        if self._program is None:
            self._program = glshaders.compileProgram(self._vertex_shader.shader, self._fragment_shader.shader)

    @property
    def vertex_layout(self) -> VertexArrayLayout:
        """Layout of the vertex array"""
        return self._vertex_layout

    @property
    def program(self) -> int:
        """The program to use for rendering."""
        if self._program is None:
            raise ValueError("Shaders have not been initialized")

        return self._program

    @property
    def vertex_shader(self) -> VertexShader:
        if self._vertex_shader is None:
            raise ValueError("Shaders have not been initialized")

        return self._vertex_shader

    @property
    def fragment_shader(self) -> FragmentShader:
        if self._fragment_shader is None:
            raise ValueError("Shaders have not been initialized")

        return self._fragment_shader

    def __del__(self):
        if self._program is not None:
            gl.glDeleteProgram(self._program)
