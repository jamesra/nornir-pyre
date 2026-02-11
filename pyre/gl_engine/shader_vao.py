import ctypes

import OpenGL.GL as gl
import numpy as np
from numpy.typing import NDArray
from PyQt6.QtGui import QOpenGLContext

import pyre.gl_engine
import pyre.gl_engine.helpers
from pyre.gl_engine.helpers import check_for_error, raise_on_error
from pyre.gl_engine.vertexarraylayout import VertexArrayLayout
from pyre.gl_engine.context_aware_vao import ContextAwareVAOHelper


class ShaderVAO(ContextAwareVAOHelper):
    """
    Creates a Vertex Array Object for a set of control points and indices
    that are static and will not change during the lifetime of the object.

    This class is context-aware and will automatically create VAOs for each OpenGL context
    that uses it. The vertex and index data is stored and reused for lazy VAO creation
    in other contexts.

    Supports context manager protocol:
        with vao:
            # VAO is bound here
            # ... rendering code ...
        # VAO is automatically unbound here
    """
    _vertex_buffer: ctypes.c_uint | None = None
    _vertex_layout: VertexArrayLayout | None = None
    _vertex_data: NDArray[np.floating] | None = None
    _is_bound: bool = False

    def __init__(self,
                 layout: VertexArrayLayout,
                 verticies: NDArray[np.floating],
                 indicies: NDArray[np.uint16]):
        """
        Initialize a new ShaderVAO.

        Args:
            layout (VertexArrayLayout): The layout of the vertex data
            verticies (NDArray[np.floating]): The vertex data
            indicies (NDArray[np.uint16]): The index data
        """
        super().__init__()

        # Store data for lazy VAO creation
        self._vertex_layout = layout
        self._vertex_data = verticies
        self._indices = indicies

        # Create OpenGL objects for the current context
        self.create_open_gl_objects(layout, verticies, indicies)

    def create_open_gl_objects(self,
                               vertex_layout: VertexArrayLayout,
                               verticies: NDArray[np.floating],
                               indicies: NDArray[np.uint16]):
        """
        Create the VAO and buffers for the current context.

        This method creates a VAO, vertex buffer, and index buffer for the current
        OpenGL context and stores the VAO ID in the context dictionary.

        Args:
            vertex_layout (VertexArrayLayout): The layout of the vertex data
            verticies (NDArray[np.floating]): The vertex data
            indicies (NDArray[np.uint16]): The index data
        """
        context = QOpenGLContext.currentContext()
        if not context or not context.isValid():
            raise RuntimeError("ShaderVAO requires an active OpenGL context")

        try:
            check_for_error()

            # Create VAO
            vao_id = gl.glGenVertexArrays(1)
            if vao_id is None or vao_id == 0:
                raise RuntimeError("Failed to generate VAO")
            vao_id = int(vao_id)
            self._context_vaos[context] = vao_id
            check_for_error()

            gl.glBindVertexArray(vao_id)
            check_for_error()

            # Create vertex buffer
            vertex_buffer_id = gl.glGenBuffers(1)
            if vertex_buffer_id is None or vertex_buffer_id == 0:
                raise RuntimeError("Failed to generate vertex buffer")
            self._vertex_buffer = int(vertex_buffer_id)
            check_for_error()

            gl.glBindBuffer(gl.GL_ARRAY_BUFFER, self._vertex_buffer)
            check_for_error()

            flat_verts = verticies.flatten()
            gl.glBufferData(gl.GL_ARRAY_BUFFER, flat_verts, gl.GL_STATIC_DRAW)
            check_for_error()

            # Create index buffer
            index_buffer_id = gl.glGenBuffers(1)
            if index_buffer_id is None or index_buffer_id == 0:
                raise RuntimeError("Failed to generate index buffer")
            self._index_buffer_id = int(index_buffer_id)
            check_for_error()

            gl.glBindBuffer(gl.GL_ELEMENT_ARRAY_BUFFER, self._index_buffer_id)
            check_for_error()
            gl.glBufferData(gl.GL_ELEMENT_ARRAY_BUFFER, indicies, gl.GL_STATIC_DRAW)
            check_for_error()

            # Set up vertex attributes
            vertex_layout.add_vertex_attributes()

            # Mark as initialized
            self._initialized = True

            # Store configuration for lazy creation in other contexts
            if self._vao_config is None:
                # Note: For ShaderVAO, buffers are created per-context, not shared
                self._vao_config = {
                    'buffers': [],  # Empty since buffers are created per-context
                    'indices': indicies,
                }

        finally:
            gl.glBindVertexArray(0)
            check_for_error()

    def _create_vao_for_context(self, context: QOpenGLContext) -> int:
        """
        Create a VAO for the specified context using stored configuration.

        For ShaderVAO, this creates new vertex and index buffers for each context
        since the data is static and stored in the object.

        Args:
            context (QOpenGLContext): The OpenGL context to create the VAO for

        Returns:
            int: The OpenGL VAO ID

        Raises:
            RuntimeError: If VAO creation fails
        """
        if self._vertex_data is None or self._indices is None or self._vertex_layout is None:
            raise RuntimeError("ShaderVAO not properly initialized - missing data")

        try:
            check_for_error()

            # Create VAO
            vao_id = gl.glGenVertexArrays(1)
            if vao_id is None or vao_id == 0:
                raise RuntimeError("Failed to generate VAO")
            vao_id = int(vao_id)
            check_for_error()

            gl.glBindVertexArray(vao_id)
            check_for_error()

            # Create vertex buffer for this context
            vertex_buffer_id = gl.glGenBuffers(1)
            if vertex_buffer_id is None or vertex_buffer_id == 0:
                raise RuntimeError("Failed to generate vertex buffer")
            vertex_buffer_id = int(vertex_buffer_id)
            check_for_error()

            gl.glBindBuffer(gl.GL_ARRAY_BUFFER, vertex_buffer_id)
            check_for_error()

            flat_verts = self._vertex_data.flatten()
            gl.glBufferData(gl.GL_ARRAY_BUFFER, flat_verts, gl.GL_STATIC_DRAW)
            check_for_error()

            # Create index buffer for this context
            index_buffer_id = gl.glGenBuffers(1)
            if index_buffer_id is None or index_buffer_id == 0:
                raise RuntimeError("Failed to generate index buffer")
            index_buffer_id = int(index_buffer_id)
            check_for_error()

            gl.glBindBuffer(gl.GL_ELEMENT_ARRAY_BUFFER, index_buffer_id)
            check_for_error()
            gl.glBufferData(gl.GL_ELEMENT_ARRAY_BUFFER, self._indices, gl.GL_STATIC_DRAW)
            check_for_error()

            # Set up vertex attributes
            self._vertex_layout.add_vertex_attributes()

            # Unbind
            gl.glBindVertexArray(0)
            check_for_error()

            return vao_id

        except Exception as e:
            raise RuntimeError(f"Failed to create VAO for context: {e}") from e

    def bind(self) -> bool:
        """
        Bind the VAO to the context for rendering.

        Returns:
            bool: True if bind was successful, False otherwise
        """
        # Use parent class bind which handles lazy creation
        result = super().bind()
        if result:
            self._is_bound = True
        return result

    def unbind(self):
        """Unbind the VAO from the context."""
        if not self._is_bound:
            # Warn that we are unbinding an unbound VAO
            print("Warning: unbinding an unbound VAO")
            return

        super().unbind()
        self._is_bound = False
