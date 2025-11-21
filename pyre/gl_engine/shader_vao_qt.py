import ctypes

from OpenGL import GL as gl
from PyQt6.QtOpenGL import QOpenGLFunctions_4_1_Core as QOpenGLFunctions
import PyQt6.QtOpenGL as QtOpenGL
import numpy as np
from numpy.typing import NDArray

import pyre.gl_engine.helpers
from pyre.gl_engine.helpers import raise_on_error, check_for_error
from pyre.gl_engine.vertexarraylayout import VertexArrayLayout


class ShaderVAOQt:
    """Creates a Vertex Array Object for a set of control points and indicies
    that are static and will not change during the lifetime of the object
    using Qt's OpenGL system"""
    _vertex_buffer: int | None = None
    _index_buffer: int | None = None
    _vao: QtOpenGL.QOpenGLVertexArrayObject | int | None = None
    _num_elements: int = 0
    _gl_funcs: QOpenGLFunctions | None = None  # OpenGL functions

    @property
    def gl_funcs(self) -> QOpenGLFunctions:
        """
        Get the OpenGL functions object.

        This property provides access to the OpenGL functions used to create and
        manage the VAO. If no OpenGL functions object has been set, a new one is
        created and initialized.

        Returns:
            QOpenGLFunctions: The OpenGL functions object
        """
        if self._gl_funcs is None:
            self._gl_funcs = QOpenGLFunctions()
            self._gl_funcs.initializeOpenGLFunctions()
        return self._gl_funcs

    @property
    def num_elements(self) -> int:
        """Number of indicies in the VAO"""
        return self._num_elements

    def __init__(self,
                 layout: VertexArrayLayout,
                 verticies: NDArray[np.floating],
                 indicies: NDArray[np.uint16],
                 gl_funcs: QOpenGLFunctions = None):
        """
        Initialize a new ShaderVAOQt.

        Args:
            layout: The vertex array layout
            verticies: The vertex data
            indicies: The index data
            gl_funcs (QOpenGLFunctions, optional): OpenGL functions to use.
                If None, a new QOpenGLFunctions object will be created when needed.
        """
        self._gl_funcs = gl_funcs
        self._num_elements = len(indicies)
        self.create_open_gl_objects(layout, verticies, indicies)

    def create_open_gl_objects(self,
                               vertex_layout: VertexArrayLayout,
                               verticies: NDArray[np.floating],
                               indicies: NDArray[np.uint16]):
        """Create the VAO"""

        try:
            # Try to create and initialize the QOpenGLVertexArrayObject
            try:
                self._vao = QtOpenGL.QOpenGLVertexArrayObject()
                if not self._vao.create():
                    # Fall back to using a regular OpenGL VAO
                    self._vao = gl.glGenVertexArrays(1)
                    raise_on_error("after glGenVertexArrays in create_open_gl_objects")
                    gl.glBindVertexArray(self._vao)
                    raise_on_error("after glBindVertexArray in create_open_gl_objects")
                else:
                    if not self._vao.bind():
                        # Fall back to using a regular OpenGL VAO
                        self._vao = gl.glGenVertexArrays(1)
                        raise_on_error("after glGenVertexArrays in create_open_gl_objects (fallback)")
                        gl.glBindVertexArray(self._vao)
                        raise_on_error("after glBindVertexArray in create_open_gl_objects (fallback)")
            except Exception as e:
                # Fall back to using a regular OpenGL VAO
                print(f"Warning: Failed to create QOpenGLVertexArrayObject: {e}")
                self._vao = gl.glGenVertexArrays(1)
                raise_on_error("after glGenVertexArrays in create_open_gl_objects (exception handler)", e)
                gl.glBindVertexArray(self._vao)
                raise_on_error("after glBindVertexArray in create_open_gl_objects (exception handler)", e)

            # Create vertex buffer
            self._vertex_buffer = self.gl_funcs.glGenBuffers(1)
            raise_on_error("after glGenBuffers(vertex) in create_open_gl_objects")
            self.gl_funcs.glBindBuffer(gl.GL_ARRAY_BUFFER, self._vertex_buffer)
            raise_on_error("after glBindBuffer(vertex) in create_open_gl_objects")

            # Convert numpy array to bytes for PyQt's OpenGL functions
            flat_verts = verticies.flatten()
            vertices_bytes = flat_verts.tobytes()
            self.gl_funcs.glBufferData(gl.GL_ARRAY_BUFFER, len(vertices_bytes), vertices_bytes, gl.GL_STATIC_DRAW)
            raise_on_error("after glBufferData(vertex) in create_open_gl_objects")

            # Create index buffer
            self._index_buffer = self.gl_funcs.glGenBuffers(1)
            raise_on_error("after glGenBuffers(index) in create_open_gl_objects")
            self.gl_funcs.glBindBuffer(gl.GL_ELEMENT_ARRAY_BUFFER, self._index_buffer)
            raise_on_error("after glBindBuffer(index) in create_open_gl_objects")

            # Convert numpy array to bytes for PyQt's OpenGL functions
            indices_bytes = indicies.tobytes()
            self.gl_funcs.glBufferData(gl.GL_ELEMENT_ARRAY_BUFFER, len(indices_bytes), indices_bytes, gl.GL_STATIC_DRAW)
            raise_on_error("after glBufferData(index) in create_open_gl_objects")

            vertex_layout.add_vertex_attributes()

        finally:
            # Handle QOpenGLVertexArrayObject differently than raw VAO IDs
            if isinstance(self._vao, QtOpenGL.QOpenGLVertexArrayObject):
                self._vao.release()
            else:
                try:
                    gl.glBindVertexArray(0)
                    check_for_error("after glBindVertexArray(0) in create_open_gl_objects finally")
                except Exception as e:
                    print(f"Warning: Error unbinding VAO: {e}")
                    check_for_error("during VAO unbind exception handling in create_open_gl_objects")

    def bind(self) -> bool:
        """Bind the VAO to the context for rendering.
        Returns true if bind was successful"""
        # Handle QOpenGLVertexArrayObject differently than raw VAO IDs
        if isinstance(self._vao, QtOpenGL.QOpenGLVertexArrayObject):
            valid = self._vao.isCreated()
            if not valid:
                print(f"Warning: VAO {self._vao} is not valid in the current context")
                return False
            self._vao.bind()
        else:
            try:
                valid = gl.glIsVertexArray(self._vao)
                if not valid:
                    print(f"Warning: VAO {self._vao} is not valid in the current context")
                    return False
                try:
                    gl.glBindVertexArray(self._vao)
                except Exception as e:
                    print(f"Warning: Error binding VAO: {e}")
                    return False
            except Exception as e:
                print(f"Warning: Error checking if VAO is valid: {e}")
                return False

        raise_on_error("after glBindVertexArray in bind")
        return True

    def unbind(self):
        """Unbind the VAO from the context"""
        # Handle QOpenGLVertexArrayObject differently than raw VAO IDs
        if isinstance(self._vao, QtOpenGL.QOpenGLVertexArrayObject):
            self._vao.release()
        else:
            try:
                gl.glBindVertexArray(0)
                check_for_error("after glBindVertexArray(0) in unbind")
            except Exception as e:
                print(f"Warning: Error unbinding VAO: {e}")
                check_for_error("during VAO unbind exception handling")

    def __del__(self):
        """Clean up OpenGL resources when the object is deleted"""
        if self._vao is not None:
            # Handle QOpenGLVertexArrayObject differently than raw VAO IDs
            if isinstance(self._vao, QtOpenGL.QOpenGLVertexArrayObject):
                self._vao.destroy()
            else:
                gl.glDeleteVertexArrays(1, [self._vao])
            self._vao = None

        if self._vertex_buffer is not None:
            self.gl_funcs.glDeleteBuffers(1, [self._vertex_buffer])
            self._vertex_buffer = None

        if self._index_buffer is not None:
            self.gl_funcs.glDeleteBuffers(1, [self._index_buffer])
            self._index_buffer = None
