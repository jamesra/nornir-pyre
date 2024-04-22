import abc
from typing import NamedTuple

from OpenGL import GL as gl
from OpenGL.GL import shaders as glshaders


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


class VertexAttribute(NamedTuple):
    location: int  # location of the variable in the compiled shader
    name: str  # Variable name of the attribute in the shader
    num_elements: int  # Number of elements in the attribute, ex: 3 for a vec3 in the shader
    type: int  # type of the elements in the attribute ex: GL_FLOAT
    type_size: int  # size of the type in bytes
    offset: int  # Offset in bytes from the start of the vertex buffer to the first element of this attribute


class BaseShader(abc.ABC):
    """Shared code for shaders."""
    _vertex_shader: VertexShader = None
    _fragment_shader: FragmentShader = None
    _program: int | None = None

    @classmethod
    @property
    def program(cls) -> int:
        """The program to use for rendering."""
        if cls._program is None:
            raise ValueError("Shaders have not been initialized")

        return cls._program

    @classmethod
    @property
    def vertex_shader(cls) -> VertexShader:
        if cls._vertex_shader is None:
            raise ValueError("Shaders have not been initialized")

        return cls._vertex_shader

    @classmethod
    @property
    def fragment_shader(cls) -> FragmentShader:
        if cls._fragment_shader is None:
            raise ValueError("Shaders have not been initialized")

        return cls._fragment_shader

    @classmethod
    @abc.abstractmethod
    def initialize(cls):
        """Called after the OpenGL context is created to initialize the shader."""
        raise NotImplementedError()

    @classmethod
    @abc.abstractmethod
    def get_attributes(cls) -> tuple[VertexAttribute]:
        """Returns the attributes for the shader."""
        raise NotImplementedError()

    @classmethod
    @property
    def attribute_stride(cls) -> int:
        """Returns the stride of the attributes in the vertex buffer."""
        return sum(attr.num_elements * attr.type_size for attr in cls.attributes)

    def __del__(self):
        gl.glDeleteProgram(self.program)
