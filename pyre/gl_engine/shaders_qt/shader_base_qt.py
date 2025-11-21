from abc import ABC

from PyQt6.QtOpenGL import QOpenGLShader, QOpenGLShaderProgram
from PyQt6.QtGui import QOpenGLContext
import OpenGL.GL as gl

from pyre.gl_engine.helpers import raise_on_error
from pyre.gl_engine.vertexarraylayout import VertexArrayLayout


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
    raise_on_error("after glActiveTexture in bind_texture")
    gl.glBindTexture(gl.GL_TEXTURE_2D, texture)
    raise_on_error("after glBindTexture in bind_texture")

    # Assign the sampler to the texture we just bound
    offset = gl_texture - gl.GL_TEXTURE0
    gl.glUniform1i(texture_location, offset)
    raise_on_error("after glUniform1i in bind_texture")


class VertexShader:
    _shader: QOpenGLShader | None = None  # The compiled shader
    _program: str
    _initialized: bool = False  # Whether the shader has been compiled

    @property
    def shader(self) -> QOpenGLShader:
        return self._shader

    def __init__(self, vertex_shader_program: str):
        self._program = vertex_shader_program

    def initialize_gl_objects(self):
        if not self._initialized:
            # Create a QOpenGLShader for the vertex shader
            self._shader = QOpenGLShader(QOpenGLShader.ShaderTypeBit.Vertex)
            # Compile the shader from the source code
            if not self._shader.compileSourceCode(self._program):
                raise ValueError(f"Failed to compile vertex shader: {self._shader.log()}")
            self._initialized = True
            raise_on_error("after initialize_gl_objects in VertexShader")

    def __del__(self):
        # QOpenGLShader objects are automatically deleted when they go out of scope
        pass


class FragmentShader:
    _shader: QOpenGLShader | None = None  # The compiled shader
    _program: str
    _initialized: bool = False  # Whether the shader has been compiled

    @property
    def shader(self) -> QOpenGLShader:
        return self._shader

    def __init__(self, fragment_shader_program: str):
        self._program = fragment_shader_program

    def initialize_gl_objects(self):
        if not self._initialized:
            # Create a QOpenGLShader for the fragment shader
            self._shader = QOpenGLShader(QOpenGLShader.ShaderTypeBit.Fragment)
            # Compile the shader from the source code
            if not self._shader.compileSourceCode(self._program):
                raise ValueError(f"Failed to compile fragment shader: {self._shader.log()}")
            self._initialized = True
            raise_on_error("after initialize_gl_objects in FragmentShader")

    def __del__(self):
        # QOpenGLShader objects are automatically deleted when they go out of scope
        pass


class BaseShader(ABC):
    """Shared code for shaders using Qt's OpenGL system."""
    _vertex_shader: VertexShader
    _fragment_shader: FragmentShader
    _program: QOpenGLShaderProgram | None = None
    _initialized: bool = False  # Track initialization state

    _vertex_layout: VertexArrayLayout

    def initialize_gl_objects(self):
        """Compile the shaders and programs using Qt's OpenGL system."""
        if self._initialized:
            return  # Already initialized
        
        self._vertex_shader.initialize_gl_objects()
        self._fragment_shader.initialize_gl_objects()

        if self._program is None:
            # Create a new shader program
            self._program = QOpenGLShaderProgram()

            # Add the vertex and fragment shaders to the program
            if not self._program.addShader(self._vertex_shader.shader):
                raise ValueError(f"Failed to add vertex shader to program: {self._program.log()}")

            if not self._program.addShader(self._fragment_shader.shader):
                raise ValueError(f"Failed to add fragment shader to program: {self._program.log()}")

            # Link the program
            if not self._program.link():
                raise ValueError(f"Failed to link shader program: {self._program.log()}")
            
            raise_on_error("after initialize_gl_objects in BaseShader")
        
        self._initialized = True

    @property
    def vertex_layout(self) -> VertexArrayLayout:
        """Layout of the vertex array"""
        return self._vertex_layout

    @property
    def program(self) -> QOpenGLShaderProgram:
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
        # QOpenGLShaderProgram objects are automatically deleted when they go out of scope
        pass
