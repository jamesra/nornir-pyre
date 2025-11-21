"""
Implementation of Vertex Array Objects (VAOs) for instanced rendering.

This module provides the InstancedVAO class, which manages OpenGL Vertex Array Objects
for instanced rendering. Instanced rendering allows drawing multiple instances of the
same geometry with different attributes in a single draw call, which is more efficient
than drawing each instance separately.

The InstancedVAO class handles the creation, initialization, binding, and cleanup of
VAOs, as well as the management of associated buffers (vertex buffers, instance buffers,
and index buffers).

Classes:
    InstancedVAO: Manages Vertex Array Objects for instanced rendering
"""

import ctypes

from OpenGL import GL as gl
import PyQt6.QtOpenGL as QtOpenGL
from PyQt6.QtGui import QOpenGLContext
import numpy as np
from numpy._typing import NDArray

import pyre.gl_engine
from pyre.gl_engine import raise_on_error, check_for_error
from pyre.gl_engine.interfaces import IBuffer


class InstancedVAO:
    """
    Manages Vertex Array Objects (VAOs) for instanced rendering.

    This class provides functionality for creating and managing OpenGL Vertex Array Objects
    that can be used for instanced rendering. It handles the initialization, binding, and
    cleanup of VAOs, as well as the management of associated buffers.

    The initialization of a VAO is a multi-step process:
    1. Call begin_init() to start the initialization process
    2. Add buffers using add_buffer() for vertex and instance data
    3. Add an index buffer using add_index_buffer() for indexed rendering
    4. Call end_init() to complete the initialization

    After initialization, the VAO can be bound for rendering using the bind() method
    and unbound using the unbind() method.

    Attributes:
        _buffers (set[IBuffer]): Set of buffers associated with this VAO
        _indicies (NDArray[np.uint16] | None): Index data for indexed rendering
        _vao (int | None): OpenGL VAO object ID
        _num_elements (int): Number of elements in the VAO
        _intializing (bool): Flag indicating if the VAO is being initialized
        _initialized (bool): Flag indicating if the VAO has been initialized
        _index_buffer (int | None): OpenGL index buffer object ID
        _gl_funcs (QOpenGLFunctions | None): OpenGL functions
    """
    _buffers: set[IBuffer]
    _indicies: NDArray[np.uint16] | None = None
    _vao: int | None = None
    _num_elements: int = 0
    _intializing: bool = False
    _initialized: bool = False
    _index_buffer: int | None = None  # The index buffer

    @property
    def num_elements(self) -> int:
        """
        Get the number of elements (indices) in the VAO.

        This property returns the number of indices in the index buffer,
        which determines how many elements will be rendered when the VAO is drawn.

        Returns:
            int: The number of indices in the VAO
        """
        if self._indicies is None:
            return 0
        
        return len(self._indicies)

    def __init__(self):
        """
        Initialize a new InstancedVAO.

        Creates a new Vertex Array Object for instanced rendering. The VAO is not
        fully initialized until begin_init(), add_buffer(), add_index_buffer(),
        and end_init() have been called in sequence.

        Args:
            gl_funcs (QOpenGLFunctions, optional): OpenGL functions to use.
                If None, a new QOpenGLFunctions object will be created when needed.
        """ 

    def begin_init(self):
        """
        Begin the initialization process for the VAO.

        This method must be called before adding any buffers to the VAO.
        It creates a new OpenGL Vertex Array Object and prepares it for
        buffer attachment.

        Raises:
            ValueError: If the VAO is already initialized or initializing
            RuntimeError: If no valid OpenGL context is current
        """
        if self._initialized:
            raise ValueError("VAO already initialized")
        if self._intializing:
            raise ValueError("VAO already initializing")

        # Validate that we have an active OpenGL context before creating VAO
        
        context = QOpenGLContext.currentContext()
        if not context or not context.isValid():
            raise RuntimeError(
                "InstancedVAO.begin_init() requires an active OpenGL context. "
                "This error often manifests as 'Out of Memory' in PyQt6. "
                "Ensure the context is current before creating VAO objects."
            )

        self._intializing = True

        self._buffers = set()

        # For PyQt6 with OpenGL 4.1+ Core Profile, use raw OpenGL VAO directly
        # QOpenGLVertexArrayObject has issues with context sharing in some configurations
        try:
            self._vao = gl.glGenVertexArrays(1)
            if self._vao == 0:
                raise RuntimeError("glGenVertexArrays returned 0 (invalid VAO)")
            raise_on_error("after glGenVertexArrays in begin_init", RuntimeError("glGenVertexArrays failed"))
            
            gl.glBindVertexArray(self._vao)
            raise_on_error("after glBindVertexArray in begin_init")
                
        except Exception as e:
            raise RuntimeError(
                f"Failed to create VAO using glGenVertexArrays: {e}. "
                f"This usually indicates no valid OpenGL context is current, "
                f"or the OpenGL driver is in an error state."
            ) from e

        # Commented code preserved for reference
        # self.gl_funcs.glBufferData(
        #     gl.GL_ELEMENT_ARRAY_BUFFER,
        #     self._indicies,
        #     gl.GL_STATIC_DRAW
        # )
        # self.gl_funcs.glBindVertexArray(self._vao)

    def end_init(self):
        """
        Complete the initialization process for the VAO.

        This method must be called after adding all buffers to the VAO.
        It finalizes the VAO configuration and validates that all required
        buffers have been added.

        Raises:
            ValueError: If the VAO is not initializing, is already initialized,
                       has no index buffer, has no buffers, or is not valid
        """
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
            check_for_error("during VAO unbind exception handling in end_init")

    def add_index_buffer(self, indicies: NDArray[np.uint16]):
        """
        Add an index buffer to the VAO.

        This method creates an OpenGL buffer for the provided indices and
        binds it to the VAO. The index buffer is used for indexed rendering,
        which allows reusing vertices.

        Args:
            indicies (NDArray[np.uint16]): Array of indices referencing vertices
                                          in the vertex buffer

        Raises:
            ValueError: If the VAO is not initializing or is already initialized
        """
        raise_on_error("before glGenBuffers in add_index_buffer")
        if not self._intializing:
            raise ValueError("VAO not initializing")
        if self._initialized:
            raise ValueError("VAO already initialized")

        self._indicies = indicies
        self._index_buffer = gl.glGenBuffers(1)
        raise_on_error("after glGenBuffers in add_index_buffer")
        gl.glBindBuffer(gl.GL_ELEMENT_ARRAY_BUFFER, self._index_buffer)
        raise_on_error("after glBindBuffer(GL_ELEMENT_ARRAY_BUFFER) in add_index_buffer")
        # Convert numpy array to bytes for PyQt's OpenGL functions  
        gl.glBufferData(gl.GL_ELEMENT_ARRAY_BUFFER, indicies, gl.GL_STATIC_DRAW)
        raise_on_error("after glBufferData in add_index_buffer")

    def add_buffer(self, buffer: IBuffer):
        """
        Add a buffer to the VAO.

        This method adds either a vertex buffer or an instance buffer to the VAO.
        The buffer's layout is used to set up the vertex attributes for the VAO.

        Args:
            buffer (IBuffer): The buffer to add to the VAO. This can be a vertex buffer
                             containing vertex data or an instance buffer containing
                             per-instance data.

        Raises:
            ValueError: If the VAO is not initializing, is already initialized,
                       or if the buffer has already been added
        """
        raise_on_error("before glGenBuffers in add_buffer")
        if not self._intializing:
            raise ValueError("VAO not initializing")
        if self._initialized:
            raise ValueError("VAO already initialized")

        if buffer in self._buffers:
            raise ValueError("Buffer already added to VAO")

        self._buffers.add(buffer)
        gl.glBindBuffer(gl.GL_ARRAY_BUFFER, buffer.buffer)
        buffer.layout.add_vertex_attributes()
        gl.glBindBuffer(gl.GL_ARRAY_BUFFER, 0)

    def bind(self) -> bool:
        """
        Bind the VAO to the current OpenGL context for rendering.

        This method makes the VAO active for subsequent rendering operations.

        Returns:
            bool: True if the VAO was successfully bound, False otherwise
        """
        try:
            gl.glBindVertexArray(self._vao)
            raise_on_error("after glBindVertexArray in bind")
            return True
        except Exception as e:
            print(f"Error binding VAO: {e}")
            return False

    def unbind(self):
        """
        Unbind the VAO from the current OpenGL context.

        This method deactivates the VAO for subsequent rendering operations
        by binding VAO 0 (no VAO).
        """
        # Handle QOpenGLVertexArrayObject differently than raw VAO IDs
        if isinstance(self._vao, QtOpenGL.QOpenGLVertexArrayObject):
            self._vao.release()
        else:
            try:
                gl.glBindVertexArray(0)
            except Exception as e:
                print(f"Warning: Error unbinding VAO: {e}")
        pyre.gl_engine.helpers.raise_on_error()

    def __del__(self):
        """
        Clean up OpenGL resources when the object is deleted.

        This destructor ensures that the VAO and index buffer are properly
        deleted when the object is garbage collected, preventing OpenGL
        resource leaks.
        """
        if self._vao is not None:
            # Handle QOpenGLVertexArrayObject differently than raw VAO IDs
            if isinstance(self._vao, QtOpenGL.QOpenGLVertexArrayObject):
                self._vao.destroy()
            else:
                gl.glDeleteVertexArrays(1, [self._vao])
            raise_on_error("after glDeleteVertexArrays in __del__")
            self._vao = None
            

        if self._index_buffer is not None:
            self.gl_funcs.glDeleteBuffers(1, [self._index_buffer])
            raise_on_error("after glDeleteVertexArrays in __del__")
            self._index_buffer = None
