import ctypes

from OpenGL import GL as gl
from PyQt6.QtOpenGL import QOpenGLFunctions_4_1_Core as QOpenGLFunctions
import PyQt6.QtOpenGL as QtOpenGL
import numpy as np
from numpy.typing import NDArray
from PyQt6.QtGui import QOpenGLContext

from pyre.gl_engine.gl_buffer import GLIndexBuffer
import pyre.gl_engine.helpers
from pyre.gl_engine.helpers import raise_on_error, check_for_error
from pyre.gl_engine.interfaces import IBuffer, IVAO


class DynamicVAOQt(IVAO):
    """Creates a Vertex Array Object for a set of vertex data that can be updated dynamically using Qt's OpenGL system"""
    _vao: QtOpenGL.QOpenGLVertexArrayObject | int | None = None
    _intializing: bool = False
    _initialized: bool = False
    _index_buffer: GLIndexBuffer = None  # The index buffer
    _buffers: set[IBuffer] = set()  # The vertex buffers
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
        return len(self.indicies)

    @property
    def indicies(self) -> NDArray[np.integer]:
        """List of triangle indicies.  Should be in groups of three"""
        return self._index_buffer.data

    def __init__(self, gl_funcs: QOpenGLFunctions = None):
        """
        Initialize a new DynamicVAOQt.

        Args:
            gl_funcs (QOpenGLFunctions, optional): OpenGL functions to use.
                If None, a new QOpenGLFunctions object will be created when needed.
        """
        self._gl_funcs = gl_funcs

    def begin_init(self):
        """This is called once, before adding any buffers"""
        if self._initialized:
            raise ValueError("VAO already initialized")
        if self._intializing:
            raise ValueError("VAO already initializing")

        # Validate that we have an active OpenGL context before creating VAO
        context = QOpenGLContext.currentContext()
        if not context or not context.isValid():
            raise RuntimeError(
                "DynamicVAOQt.begin_init() requires an active OpenGL context."
            )

        self._intializing = True

        self._buffers = set()
        
        # Use raw OpenGL VAO directly for better compatibility
        try:
            self._vao = gl.glGenVertexArrays(1)
            if self._vao == 0:
                raise RuntimeError("glGenVertexArrays returned 0 (invalid VAO)")
            raise_on_error("after glGenVertexArrays in begin_init", RuntimeError("glGenVertexArrays failed"))
            
            gl.glBindVertexArray(self._vao)
            raise_on_error("after glBindVertexArray in begin_init")
                
        except Exception as e:
            raise RuntimeError(
                f"Failed to create VAO using glGenVertexArrays: {e}."
            ) from e

    def end_init(self):
        """This is called once, after adding all buffers"""
        if not self._intializing:
            raise ValueError("VAO not initializing")
        if self._initialized:
            raise ValueError("VAO already initialized")
        if not self._index_buffer:
            raise ValueError("Index buffer not added to VAO")
        if len(self._buffers) == 0:
            raise ValueError("No buffers added to VAO")

        self._intializing = False
        self._initialized = True

        # Unbind the VAO (cleanup code - use check_for_error to log and clear)
        try: 
            gl.glBindVertexArray(0)
            check_for_error("after glBindVertexArray(0) in end_init")
        except Exception as e:
            print(f"Warning: Error unbinding VAO: {e}")
            check_for_error("during VAO unbind exception handling")

    def add_index_buffer(self, value: GLIndexBuffer):
        """Adds the index buffer to the VAO"""
        if not self._intializing:
            raise ValueError("VAO not initializing")
        if self._initialized:
            raise ValueError("VAO already initialized")

        self._index_buffer = value
        gl.glBindBuffer(gl.GL_ELEMENT_ARRAY_BUFFER, self._index_buffer.buffer)
        raise_on_error("after glBindBuffer(GL_ELEMENT_ARRAY_BUFFER) in add_index_buffer")

    def add_buffer(self, buffer: IBuffer):
        """
        Add either a vertex buffer or an instance buffer to the VAO
        :param buffer:
        :return:
        """
        if not self._intializing:
            raise ValueError("VAO not initializing")
        if self._initialized:
            raise ValueError("VAO already initialized")

        if buffer in self._buffers:
            raise ValueError("Buffer already added to VAO")

        self._buffers.add(buffer)
        gl.glBindBuffer(gl.GL_ARRAY_BUFFER, buffer.buffer)
        raise_on_error("after glBindBuffer(GL_ARRAY_BUFFER) in add_buffer")

        buffer.layout.add_vertex_attributes()

    def bind(self) -> bool:
        """Bind the VAO to the context for rendering"""
        try:
            gl.glBindVertexArray(self._vao)
            raise_on_error("after glBindVertexArray in bind")
            return True
        except Exception as e:
            print(f"Error binding VAO: {e}")
            return False

    def unbind(self):
        """Unbind the VAO from the context"""
        try: 
            gl.glBindVertexArray(0)
            check_for_error("after glBindVertexArray(0) in unbind")
        except Exception as e:
            # Don't print the warning - it's not critical
            check_for_error("during VAO unbind exception handling")
            pass

    def __del__(self):
        """Clean up OpenGL resources when the object is deleted"""
        if self._vao is not None:
            try:
                gl.glDeleteVertexArrays(1, [self._vao])
            except Exception:
                pass  # Context may no longer be valid during cleanup
            self._vao = None