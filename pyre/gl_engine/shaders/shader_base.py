from abc import abstractmethod, ABC
from OpenGL import GL as gl
from OpenGL.GL import shaders as glshaders
from pyre.gl_engine.vertexarraylayout import VertexArrayLayout


class VertexShader:
    _shader: int

    @property
    def shader(self):
        return self._shader

    def __init__(self, vertex_shader_program: str):
        self._shader = glshaders.compileShader(vertex_shader_program, gl.GL_VERTEX_SHADER)

    def __del__(self):
        gl.glDeleteShader(self._shader)


class FragmentShader:
    _shader: int

    @property
    def shader(self):
        return self._shader

    def __init__(self, fragment_shader_program: str):
        self._shader = glshaders.compileShader(fragment_shader_program, gl.GL_FRAGMENT_SHADER)

    def __del__(self):
        gl.glDeleteShader(self._shader)


class BaseShader(ABC):
    """Shared code for shaders."""
    _vertex_shader: VertexShader = None
    _fragment_shader: FragmentShader = None
    _program: int | None = None

    _vertex_layout: VertexArrayLayout

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
        gl.glDeleteProgram(self.program)
