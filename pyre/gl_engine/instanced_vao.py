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
from PyQt6.QtGui import QOpenGLContext
import numpy as np
from numpy._typing import NDArray

import pyre.gl_engine
from pyre.gl_engine import raise_on_error, check_for_error
from pyre.gl_engine.interfaces import IBuffer
from pyre.gl_engine.context_aware_vao import ContextAwareVAOHelper


class InstancedVAO(ContextAwareVAOHelper):
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

    This class is context-aware and will automatically create VAOs for each OpenGL context
    that uses it. The configuration is stored after the first initialization and reused
    for lazy VAO creation in other contexts.

    Supports context manager protocol:
        with vao:
            # VAO is bound here
            # ... rendering code ...
        # VAO is automatically unbound here
    """

    def __init__(self):
        """
        Initialize a new InstancedVAO.

        Creates a new Vertex Array Object for instanced rendering. The VAO is not
        fully initialized until begin_init(), add_buffer(), add_index_buffer(),
        and end_init() have been called in sequence.
        """
        super().__init__()

    def begin_init(self):
        """
        Begin the initialization process for the VAO.

        This method must be called before adding any buffers to the VAO.
        It validates the OpenGL context and prepares for buffer attachment.
        On first call, it creates a VAO for the current context. On subsequent
        calls, it allows re-initialization for additional contexts.

        Raises:
            ValueError: If the VAO is already initializing
            RuntimeError: If no valid OpenGL context is current
        """
        # Call parent to set up state
        super().begin_init()

        # If this is the first initialization, create a VAO for the current context
        if not self.is_initialized:
            context = QOpenGLContext.currentContext()
            try:
                vao_id = gl.glGenVertexArrays(1)
                if vao_id == 0:
                    raise RuntimeError("glGenVertexArrays returned 0 (invalid VAO)")
                raise_on_error("after glGenVertexArrays in begin_init", RuntimeError("glGenVertexArrays failed"))

                assert context is not None
                self._context_vaos[context] = vao_id
                gl.glBindVertexArray(vao_id)
                raise_on_error("after glBindVertexArray in begin_init")

            except Exception as e:
                raise RuntimeError(
                    f"Failed to create VAO using glGenVertexArrays: {e}. "
                    f"This usually indicates no valid OpenGL context is current, "
                    f"or the OpenGL driver is in an error state."
                ) from e

    def end_init(self):
        """
        Complete the initialization process for the VAO.

        This method must be called after adding all buffers to the VAO.
        It finalizes the VAO configuration and stores it for lazy creation
        in other contexts.

        Raises:
            ValueError: If the VAO is not initializing, has no index buffer,
                       or has no buffers
        """
        # Call parent to finalize initialization
        super().end_init()

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
            ValueError: If the VAO is not initializing
        """
        raise_on_error("before glGenBuffers in add_index_buffer")
        if not self._initializing:
            raise ValueError("VAO not initializing")

        # Store indices for lazy VAO creation
        self._indices = indicies

        # Create index buffer
        self._index_buffer_id = gl.glGenBuffers(1)
        raise_on_error("after glGenBuffers in add_index_buffer")
        gl.glBindBuffer(gl.GL_ELEMENT_ARRAY_BUFFER, self._index_buffer_id)
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
            ValueError: If the VAO is not initializing or if the buffer has already been added
        """
        raise_on_error("before add_buffer")
        if not self._initializing:
            raise ValueError("VAO not initializing")

        if buffer in self._buffers:
            raise ValueError("Buffer already added to VAO")

        self._buffers.add(buffer)
        gl.glBindBuffer(gl.GL_ARRAY_BUFFER, buffer.buffer)
        buffer.layout.add_vertex_attributes()
        gl.glBindBuffer(gl.GL_ARRAY_BUFFER, 0)

    def _create_vao_for_context(self, context: QOpenGLContext) -> int:
        """
        Create a VAO for the specified context using stored configuration.

        This method creates and configures a VAO for a specific context using
        the stored buffer and index configuration.

        Args:
            context (QOpenGLContext): The OpenGL context to create the VAO for

        Returns:
            int: The OpenGL VAO ID

        Raises:
            RuntimeError: If VAO creation fails
        """
        # Create VAO
        vao_id = gl.glGenVertexArrays(1)
        if vao_id == 0:
            raise RuntimeError("glGenVertexArrays returned 0 (invalid VAO)")
        raise_on_error("after glGenVertexArrays in _create_vao_for_context")

        # Bind and configure the VAO
        gl.glBindVertexArray(vao_id)
        raise_on_error("after glBindVertexArray in _create_vao_for_context")

        # Add all buffers from stored configuration
        if self._vao_config:
            for buffer in self._vao_config['buffers']:
                gl.glBindBuffer(gl.GL_ARRAY_BUFFER, buffer.buffer)
                raise_on_error("after glBindBuffer in _create_vao_for_context")
                buffer.layout.add_vertex_attributes()

        # Bind index buffer (shared across contexts)
        if self._index_buffer_id is not None:
            gl.glBindBuffer(gl.GL_ELEMENT_ARRAY_BUFFER, self._index_buffer_id)
            raise_on_error("after glBindBuffer(GL_ELEMENT_ARRAY_BUFFER) in _create_vao_for_context")

        # Unbind
        gl.glBindVertexArray(0)
        check_for_error("after glBindVertexArray(0) in _create_vao_for_context")

        return vao_id
