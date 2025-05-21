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
from PyQt6.QtOpenGL import QOpenGLFunctions_4_1_Core as QOpenGLFunctions
import PyQt6.QtOpenGL as QtOpenGL
import numpy as np
from numpy._typing import NDArray

import pyre.gl_engine
from pyre.gl_engine import check_for_error
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
        """
        Get the number of elements (indices) in the VAO.

        This property returns the number of indices in the index buffer,
        which determines how many elements will be rendered when the VAO is drawn.

        Returns:
            int: The number of indices in the VAO
        """
        return len(self._indicies)

    def __init__(self, gl_funcs: QOpenGLFunctions = None):
        """
        Initialize a new InstancedVAO.

        Creates a new Vertex Array Object for instanced rendering. The VAO is not
        fully initialized until begin_init(), add_buffer(), add_index_buffer(),
        and end_init() have been called in sequence.

        Args:
            gl_funcs (QOpenGLFunctions, optional): OpenGL functions to use.
                If None, a new QOpenGLFunctions object will be created when needed.
        """
        self._gl_funcs = gl_funcs

    def begin_init(self):
        """
        Begin the initialization process for the VAO.

        This method must be called before adding any buffers to the VAO.
        It creates a new OpenGL Vertex Array Object and prepares it for
        buffer attachment.

        Raises:
            ValueError: If the VAO is already initialized or initializing
        """
        if self._initialized:
            raise ValueError("VAO already initialized")
        if self._intializing:
            raise ValueError("VAO already initializing")

        self._intializing = True

        self._buffers = set()
        self._vao = QtOpenGL.QOpenGLVertexArrayObject(None)
        self._vao.bind()
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

        valid = self.gl_funcs.glIsVertexArray(self._vao)
        if not valid:
            raise ValueError("VAO is not valid")

        self.gl_funcs.glBindVertexArray(0)

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
        if not self._intializing:
            raise ValueError("VAO not initializing")
        if self._initialized:
            raise ValueError("VAO already initialized")

        self._indicies = indicies
        self._index_buffer = self.gl_funcs.glGenBuffers(1)
        check_for_error()
        self.gl_funcs.glBindBuffer(gl.GL_ELEMENT_ARRAY_BUFFER, self._index_buffer)
        check_for_error()
        self.gl_funcs.glBufferData(gl.GL_ELEMENT_ARRAY_BUFFER, indicies, gl.GL_STATIC_DRAW)
        check_for_error()

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
        if not self._intializing:
            raise ValueError("VAO not initializing")
        if self._initialized:
            raise ValueError("VAO already initialized")

        if buffer in self._buffers:
            raise ValueError("Buffer already added to VAO")

        self._buffers.add(buffer)
        self.gl_funcs.glBindBuffer(gl.GL_ARRAY_BUFFER, buffer.buffer)
        buffer.layout.add_vertex_attributes()
        self.gl_funcs.glBindBuffer(gl.GL_ARRAY_BUFFER, 0)

    def bind(self) -> bool:
        """
        Bind the VAO to the current OpenGL context for rendering.

        This method makes the VAO active for subsequent rendering operations.
        It first checks if the VAO is valid before binding it.

        Returns:
            bool: True if the VAO was successfully bound, False otherwise
        """
        valid = self.gl_funcs.glIsVertexArray(self._vao)
        if not valid:
            return False

        self.gl_funcs.glBindVertexArray(self._vao)
        pyre.gl_engine.helpers.check_for_error()
        return True

    def unbind(self):
        """
        Unbind the VAO from the current OpenGL context.

        This method deactivates the VAO for subsequent rendering operations
        by binding VAO 0 (no VAO).
        """
        self.gl_funcs.glBindVertexArray(0)
        pyre.gl_engine.helpers.check_for_error()

    def __del__(self):
        """
        Clean up OpenGL resources when the object is deleted.

        This destructor ensures that the VAO and index buffer are properly
        deleted when the object is garbage collected, preventing OpenGL
        resource leaks.
        """
        if self._vao is not None:
            gl.glDeleteVertexArrays(1, [self._vao])
            self._vao = None

        if self._index_buffer is not None:
            self.gl_funcs.glDeleteBuffers(1, [self._index_buffer])
            self._index_buffer = None
