import ctypes

import OpenGL.GL as gl
import numpy as np
from numpy.typing import NDArray
from PyQt6.QtGui import QOpenGLContext

from pyre.gl_engine.gl_buffer import GLIndexBuffer
import pyre.gl_engine.helpers
from pyre.gl_engine.helpers import raise_on_error, check_for_error
from pyre.gl_engine.interfaces import IBuffer, IVAO
from pyre.gl_engine.context_aware_vao import ContextAwareVAOHelper


class DynamicVAO(ContextAwareVAOHelper, IVAO):
    """
    Creates a Vertex Array Object for a set of vertex data that can be updated dynamically.

    This class is context-aware and will automatically create VAOs for each OpenGL context
    that uses it. The configuration is stored after the first initialization and reused
    for lazy VAO creation in other contexts.

    Supports context manager protocol:
        with vao:
            # VAO is bound here
            # ... rendering code ...
        # VAO is automatically unbound here
    """
    _index_buffer: GLIndexBuffer | None = None  # The index buffer object

    @property
    def num_elements(self) -> int:
        """Number of indices in the VAO"""
        if self._index_buffer is None:
            return 0
        return len(self._index_buffer.data)

    @property
    def indicies(self) -> NDArray[np.integer]:
        """List of triangle indices. Should be in groups of three"""
        if self._index_buffer is None:
            return np.array([], dtype=np.uint16)
        return self._index_buffer.data

    def __init__(self):
        """Initialize a new DynamicVAO."""
        super().__init__()

    def begin_init(self):
        """
        Begin the initialization process for the VAO.

        This method must be called before adding any buffers to the VAO.
        It validates the OpenGL context and prepares for buffer attachment.
        On first call, it creates a VAO for the current context.

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
                # Create and bind the VAO
                vao_id = gl.glGenVertexArrays(1)
                if vao_id == 0:
                    raise RuntimeError("glGenVertexArrays returned 0 (invalid VAO)")
                raise_on_error("after glGenVertexArrays", RuntimeError("glGenVertexArrays failed"))

                assert context is not None
                self._context_vaos[context] = vao_id
                gl.glBindVertexArray(vao_id)
                raise_on_error("after glBindVertexArray in begin_init")

            except Exception as e:
                # Check for OpenGL errors in exception handler
                check_for_error("during VAO creation exception handling")
                raise RuntimeError(
                    f"Failed to create VAO using glGenVertexArrays: {e}. "
                    f"This usually indicates no valid OpenGL context is current or the context is in an error state."
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

        gl.glBindVertexArray(0)

        # Validate the VAO
        context = QOpenGLContext.currentContext()
        if context in self._context_vaos:
            vao_id = self._context_vaos[context]
            valid = gl.glIsVertexArray(vao_id)
            if not valid:
                raise ValueError("VAO is not valid")

    def add_index_buffer(self, value: GLIndexBuffer):
        """
        Adds the index buffer to the VAO.

        Args:
            value (GLIndexBuffer): The index buffer to add

        Raises:
            ValueError: If the VAO is not initializing
        """
        if not self._initializing:
            raise ValueError("VAO not initializing")

        # Store the index buffer object and its data
        self._index_buffer = value
        self._indices = value.data
        self._index_buffer_id = int(value.buffer) if value.buffer is not None else None

        # Bind the index buffer to the VAO
        gl.glBindBuffer(gl.GL_ELEMENT_ARRAY_BUFFER, self._index_buffer.buffer)
        raise_on_error("after glBindBuffer(GL_ELEMENT_ARRAY_BUFFER) in add_index_buffer")

    def add_buffer(self, buffer: IBuffer):
        """
        Add either a vertex buffer or an instance buffer to the VAO.

        Args:
            buffer (IBuffer): The buffer to add to the VAO

        Raises:
            ValueError: If the VAO is not initializing or if the buffer has already been added
        """
        if not self._initializing:
            raise ValueError("VAO not initializing")

        if buffer in self._buffers:
            raise ValueError("Buffer already added to VAO")

        self._buffers.add(buffer)
        gl.glBindBuffer(gl.GL_ARRAY_BUFFER, buffer.buffer)
        raise_on_error("after glBindBuffer(GL_ARRAY_BUFFER) in add_buffer")

        buffer.layout.add_vertex_attributes()

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

        # Bind index buffer (the GLIndexBuffer object is shared across contexts)
        if self._index_buffer is not None:
            gl.glBindBuffer(gl.GL_ELEMENT_ARRAY_BUFFER, self._index_buffer.buffer)
            raise_on_error("after glBindBuffer(GL_ELEMENT_ARRAY_BUFFER) in _create_vao_for_context")

        # Unbind
        gl.glBindVertexArray(0)
        check_for_error("after glBindVertexArray(0) in _create_vao_for_context")

        return vao_id
