import ctypes

import OpenGL.GL as gl
import numpy as np
from numpy.typing import NDArray

import pyre.gl_engine
import pyre.gl_engine.helpers
from pyre.gl_engine.helpers import check_for_error, raise_on_error
from pyre.gl_engine.vertexarraylayout import VertexArrayLayout


class ShaderVAO:
    """Creates a Vertex Array Object for a set of control points and indicies
    that are static and will not change during the lifetime of the object"""
    _vertex_buffer: ctypes.c_uint | None
    _index_buffer: ctypes.c_uint | None
    _vao: ctypes.c_uint | None = None
    _num_elements: int = 0
    _is_bound: bool = False

    @property
    def num_elements(self) -> int:
        """Number of indicies in the VAO"""
        return self._num_elements

    def __init__(self,
                 layout: VertexArrayLayout,
                 verticies: NDArray[np.floating],
                 indicies: NDArray[np.uint16]):
        self._num_elements = len(indicies)
        self.create_open_gl_objects(layout, verticies, indicies)

    def create_open_gl_objects(self,
                               vertex_layout: VertexArrayLayout,
                               verticies: NDArray[np.floating],
                               indicies: NDArray[np.uint16]):
        """Create the VAO"""

        try:
            check_for_error()
            # glGenVertexArrays(1) returns a single integer (numpy.uintc), convert to int
            vao_id = gl.glGenVertexArrays(1)
            if vao_id is None or vao_id == 0:
                raise RuntimeError("Failed to generate VAO")
            self._vao = int(vao_id)
            check_for_error()
            gl.glBindVertexArray(self._vao)
            check_for_error()

            # glGenBuffers(1) returns a single integer (numpy.uintc), convert to int
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

            index_buffer_id = gl.glGenBuffers(1)
            if index_buffer_id is None or index_buffer_id == 0:
                raise RuntimeError("Failed to generate index buffer")
            self._index_buffer = int(index_buffer_id)
            check_for_error()
            gl.glBindBuffer(gl.GL_ELEMENT_ARRAY_BUFFER, self._index_buffer)
            check_for_error()
            gl.glBufferData(gl.GL_ELEMENT_ARRAY_BUFFER, indicies, gl.GL_STATIC_DRAW)
            check_for_error()

            vertex_layout.add_vertex_attributes()

        finally:
            gl.glBindVertexArray(0)
            check_for_error()

    def bind(self) -> bool:
        """Bind the VAO to the context for rendering.
        Returns true if bind was successful"""
        # Clear any previous errors before binding
        pyre.gl_engine.helpers.check_for_error("before glBindVertexArray in VAO.bind")

        valid = gl.glIsVertexArray(self._vao)
        if not valid:
            # Log the problem but don't crash
            print(f"Warning: VAO {self._vao} is not valid in the current context")
            return False
        # Try to bind the VAO directly
        # If the VAO is invalid, glBindVertexArray will generate an error
        try:
            # Ensure we have a valid VAO ID
            if self._vao is None or self._vao == 0:
                return False

            gl.glBindVertexArray(self._vao)
            # Check for errors after binding - if there's an error, the bind failed
            raise_on_error("after glBindVertexArray in VAO.bind")

            self._is_bound = True
            return True
        except Exception as e:
            # If glBindVertexArray raises an exception, the VAO is invalid
            # Clear any errors that might have been set
            pyre.gl_engine.helpers.check_for_error("after exception in VAO.bind")
            return False

    def unbind(self):
        if not self._is_bound:
            # Warn that we are unbinding an unbound VAO
            print("Warning: unbinding an unbound VAO")
            return
        gl.glBindVertexArray(0)
        pyre.gl_engine.raise_on_error("after glBindVertexArray(0) in unbind")
        self._is_bound = False

    def __del__(self):
        if self._vao is not None:
            gl.glDeleteVertexArrays(1, [self._vao])
            self._vao = None
            gl.glDeleteBuffers(1, [self._vertex_buffer])
            self._vertex_buffer = None
            gl.glDeleteBuffers(1, [self._index_buffer])
            self._index_buffer = None

            self._vao = None
