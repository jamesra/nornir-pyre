"""
Context-aware VAO helper for managing OpenGL Vertex Array Objects across multiple contexts.

This module provides a base class for managing VAOs that can work across multiple OpenGL
contexts. It stores VAO configuration from initialization and creates VAOs lazily when
needed for each context.

Classes:
    ContextAwareVAOHelper: Base class for context-aware VAO management
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional
import ctypes

from OpenGL import GL as gl
from PyQt6.QtGui import QOpenGLContext
import numpy as np
from numpy.typing import NDArray

from pyre.gl_engine.helpers import raise_on_error, check_for_error
from pyre.gl_engine.interfaces import IBuffer


class ContextAwareVAOHelper(ABC):
    """
    Base class for managing Vertex Array Objects across multiple OpenGL contexts.

    This helper class manages per-context VAO storage using dictionaries. It stores VAO
    configuration from begin_init()/end_init() calls and creates VAOs lazily at bind()
    time for each new context.

    The class follows this lifecycle:
    1. begin_init() - Start configuration capture
    2. add_buffer()/add_index_buffer() - Configure VAO (calls are stored)
    3. end_init() - Complete configuration capture
    4. bind() - Lazily creates and binds VAO for current context
    5. unbind() - Unbinds VAO

    Attributes:
        _context_vaos (Dict[QOpenGLContext, int]): VAO IDs per context
        _vao_config (Optional[dict]): Stored configuration from first initialization
        _initialized (bool): Whether initialization has completed at least once
        _initializing (bool): Whether initialization is in progress
        _buffers (set[IBuffer]): Set of buffers associated with this VAO
        _indices (Optional[NDArray]): Index data for indexed rendering
        _index_buffer_id (Optional[int]): OpenGL index buffer ID (stored for cleanup)
    """

    _context_vaos: Dict[QOpenGLContext, int]
    _vao_config: Optional[dict]
    _initialized: bool
    _initializing: bool
    _buffers: set[IBuffer]
    _indices: Optional[NDArray]
    _index_buffer_id: Optional[int]

    def __init__(self):
        """Initialize the context-aware VAO helper."""
        self._context_vaos = {}
        self._vao_config = None
        self._initialized = False
        self._initializing = False
        self._buffers = set()
        self._indices = None
        self._index_buffer_id = None

    @property
    def num_elements(self) -> int:
        """
        Get the number of elements (indices) in the VAO.

        Returns:
            int: The number of indices in the VAO
        """
        if self._indices is None:
            return 0
        return len(self._indices)

    @property
    def is_initialized(self) -> bool:
        """
        Check if the VAO has been initialized at least once.

        Returns:
            bool: True if initialized, False otherwise
        """
        return self._initialized

    def begin_init(self):
        """
        Begin the initialization process for the VAO.

        This method must be called before adding any buffers to the VAO.
        It validates that an OpenGL context is current and prepares for
        configuration capture.

        Raises:
            ValueError: If the VAO is already initialized or initializing
            RuntimeError: If no valid OpenGL context is current
        """
        if self._initialized:
            # Allow re-initialization for additional contexts
            # Just validate we have a context
            context = QOpenGLContext.currentContext()
            if not context or not context.isValid():
                raise RuntimeError(
                    "begin_init() requires an active OpenGL context. "
                    "Ensure the context is current before initializing VAO objects."
                )
            return

        if self._initializing:
            raise ValueError("VAO already initializing")

        # Validate that we have an active OpenGL context
        context = QOpenGLContext.currentContext()
        if not context or not context.isValid():
            raise RuntimeError(
                "begin_init() requires an active OpenGL context. "
                "This error often manifests as 'Out of Memory' in PyQt6. "
                "Ensure the context is current before creating VAO objects."
            )

        self._initializing = True
        self._buffers = set()

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
        if not self._initializing:
            raise ValueError("VAO not initializing")

        if self._index_buffer_id is None and self._indices is None:
            raise ValueError("Index buffer not added to VAO")
        if len(self._buffers) == 0:
            raise ValueError("No buffers added to VAO")

        self._initializing = False
        self._initialized = True

        # Store configuration for lazy creation in other contexts
        if self._vao_config is None:
            self._vao_config = {
                'buffers': list(self._buffers),
                'indices': self._indices,
            }

    def bind(self) -> bool:
        """
        Bind the VAO to the current OpenGL context for rendering.

        This method lazily creates a VAO for the current context if one doesn't
        exist, then binds it. The VAO is configured using the stored configuration
        from the first initialization.

        Returns:
            bool: True if the VAO was successfully bound, False otherwise
        """
        if not self._initialized:
            return False

        context = QOpenGLContext.currentContext()
        if not context or not context.isValid():
            print("Warning: No valid OpenGL context for VAO bind")
            return False

        # Check if we already have a VAO for this context
        if context not in self._context_vaos:
            # Lazily create VAO for this context
            try:
                vao_id = self._create_vao_for_context(context)
                self._context_vaos[context] = vao_id
            except Exception as e:
                print(f"Error creating VAO for context: {e}")
                return False

        # Bind the VAO for this context
        vao_id = self._context_vaos[context]
        try:
            gl.glBindVertexArray(vao_id)
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
        try:
            gl.glBindVertexArray(0)
            check_for_error("after glBindVertexArray(0) in unbind")
        except Exception as e:
            print(f"Warning: Error unbinding VAO: {e}")

    def __enter__(self):
        """
        Context manager entry: bind the VAO.

        Returns:
            ContextAwareVAOHelper: This helper instance
        """
        self.bind()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Context manager exit: unbind the VAO.

        Args:
            exc_type: Exception type (if any)
            exc_val: Exception value (if any)
            exc_tb: Exception traceback (if any)

        Returns:
            bool: False to propagate exceptions
        """
        self.unbind()
        return False

    @abstractmethod
    def _create_vao_for_context(self, context: QOpenGLContext) -> int:
        """
        Create a VAO for the specified context using stored configuration.

        This method must be implemented by subclasses to create and configure
        a VAO for a specific context.

        Args:
            context (QOpenGLContext): The OpenGL context to create the VAO for

        Returns:
            int: The OpenGL VAO ID

        Raises:
            RuntimeError: If VAO creation fails
        """
        raise NotImplementedError("Subclasses must implement _create_vao_for_context")

    def _configure_vao(self, vao_id: int):
        """
        Configure the VAO with stored buffers and indices.

        This is a helper method that can be called by subclasses during VAO creation.
        It applies the stored configuration (buffers and indices) to the given VAO.

        Args:
            vao_id (int): The VAO ID to configure
        """
        # Bind the VAO
        gl.glBindVertexArray(vao_id)
        raise_on_error("after glBindVertexArray in _configure_vao")

        # Add all buffers
        if self._vao_config:
            for buffer in self._vao_config['buffers']:
                gl.glBindBuffer(gl.GL_ARRAY_BUFFER, buffer.buffer)
                raise_on_error("after glBindBuffer in _configure_vao")
                buffer.layout.add_vertex_attributes()

        # Add index buffer
        if self._indices is not None and self._index_buffer_id is not None:
            gl.glBindBuffer(gl.GL_ELEMENT_ARRAY_BUFFER, self._index_buffer_id)
            raise_on_error("after glBindBuffer(GL_ELEMENT_ARRAY_BUFFER) in _configure_vao")

        # Unbind
        gl.glBindVertexArray(0)
        check_for_error("after glBindVertexArray(0) in _configure_vao")

    def cleanup(self):
        """
        Clean up OpenGL resources for all contexts.

        This method should be called when the VAO is no longer needed.
        It deletes all VAOs and associated buffers for all contexts.

        Note: This must be called with a valid OpenGL context current.
        """
        # Delete all VAOs for all contexts
        for context, vao_id in list(self._context_vaos.items()):
            # Only delete if the context is still valid
            if context and context.isValid():
                # We can only delete resources when their context is current
                current_context = QOpenGLContext.currentContext()
                if current_context == context:
                    try:
                        gl.glDeleteVertexArrays(1, [vao_id])
                        check_for_error(f"after glDeleteVertexArrays for context {context}")
                    except Exception as e:
                        print(f"Warning: Error deleting VAO for context {context}: {e}")

        self._context_vaos.clear()

        # Delete index buffer if we own it
        if self._index_buffer_id is not None:
            try:
                gl.glDeleteBuffers(1, [self._index_buffer_id])
                check_for_error("after glDeleteBuffers for index buffer")
                self._index_buffer_id = None
            except Exception as e:
                print(f"Warning: Error deleting index buffer: {e}")

    def __del__(self):
        """
        Clean up OpenGL resources when the object is deleted.

        This destructor attempts to clean up VAOs, but may not be able to
        delete resources if the appropriate context is not current.
        """
        # Try to clean up, but don't raise exceptions in __del__
        try:
            self.cleanup()
        except Exception as e:
            print(f"Warning: Error during VAO cleanup in __del__: {e}")
