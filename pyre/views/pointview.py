"""
Point visualization module for the Pyre application.

This module provides functionality for rendering control points with textures
in OpenGL. It defines the PointView class, which manages the storage and rendering
of a set of points, each with an associated texture.

The module is used for visualizing control points in image registration tasks,
where points are placed on corresponding features in different images to establish
registration relationships.

Classes:
    PointView: Manages and renders a set of points with associated textures
"""
import OpenGL.GL as gl
import numpy as np
from numpy.typing import NDArray
from PyQt6.QtOpenGL import QOpenGLFunctions_4_1_Core as QOpenGLFunctions

import pyre
from pyre.controllers import TransformController
from pyre.gl_engine import GLBuffer, GLIndexBuffer, InstancedVAO, get_texture_array_length
from pyre.gl_engine.shaders import ControlPointSetShader


class PointView:
    """
    Manages and renders a set of points with associated textures in OpenGL.

    This class provides functionality for storing and rendering control points
    in OpenGL using instanced rendering. Each point is rendered as a billboard
    texture (a quad that always faces the camera) with a specific texture from
    a texture array. Instance texture index 2 is busy: the shader keeps the
    glyph upright and grey and draws a spinning comet arc outside it.

    The class manages the OpenGL resources needed for rendering, including
    vertex buffers, instance buffers, and vertex array objects. It provides
    properties for accessing and modifying the points and their associated
    texture indices.

    Attributes:
        _texture_array (int): OpenGL texture array ID
        _vertex_buffer (GLBuffer | None): Buffer for vertex data
        _point_buffer (GLBuffer): Buffer for point positions
        _texture_buffer (GLBuffer): Buffer for texture indices
        _vao (InstancedVAO): Vertex array object for rendering
        _num_textures (int): Number of textures in the texture array
        _gl_funcs (QOpenGLFunctions | None): OpenGL functions
    """
    _texture_array: int  # The texture array
    _vertex_buffer: GLBuffer | None  # A single vertex array represents all points.  We scale the model matrix to render.
    _point_buffer: GLBuffer  # The points to render
    _texture_buffer: GLBuffer  # The texture index for each point
    _vao: InstancedVAO  # The vertex array object

    _num_textures: int  # The number of textures in the texture array

    _gl_funcs: QOpenGLFunctions | None = None  # OpenGL functions

    @property
    def gl_funcs(self) -> QOpenGLFunctions:
        """
        Get the OpenGL functions object.

        This property provides access to the OpenGL functions used for rendering.
        If no OpenGL functions object has been set, a new one is created and initialized.

        Returns:
            QOpenGLFunctions: The OpenGL functions object
        """
        if self._gl_funcs is None:
            self._gl_funcs = QOpenGLFunctions()
            self._gl_funcs.initializeOpenGLFunctions()
        return self._gl_funcs

    @property
    def num_textures(self) -> int:
        """
        Get the number of textures in the texture array.

        This property returns the number of textures available in the texture array,
        which can be used to validate texture indices.

        Returns:
            int: The number of textures in the texture array
        """
        return self._num_textures

    @property
    def texture(self) -> int:
        """
        Get the texture array ID.

        This property returns the OpenGL texture array ID that contains
        the textures used for rendering the points.

        Returns:
            int: The OpenGL texture array ID
        """
        return self._texture_array

    @texture.setter
    def texture(self, value: int):
        """
        Set the texture array ID.

        This setter allows changing the texture array used for rendering the points.

        Args:
            value (int): The new OpenGL texture array ID
        """
        self._texture_array = value

    @property
    def points(self) -> NDArray[np.floating]:
        """
        Get the array of point positions.

        This property returns the array of point positions that are being rendered.
        The points are stored in the point buffer and are used for instanced rendering.

        Returns:
            NDArray[np.floating]: Array of point positions
        """
        return self._point_buffer.data  # type: ignore[return-value]

    @points.setter
    def points(self, value: NDArray[np.floating]):
        """
        Set the array of point positions.

        This setter allows changing the points that are being rendered. The input
        array is converted to float32 and the columns are swapped to match the
        OpenGL coordinate system (XY instead of YX).

        Args:
            value (NDArray[np.floating]): New array of point positions
        """
        # OpenGL buffer upload requires host memory; convert CuPy to numpy if needed
        value = value.get() if hasattr(value, "get") else value  # type: ignore[attr-defined]
        value = np.asarray(value, dtype=np.float32)
        gl_value = TransformController.swap_columns_to_XY(value)
        self._point_buffer.data = gl_value
        # Keep per-instance texture indices aligned with point count.
        # A stale/short texture buffer can cause invalid GPU reads during instanced draw.
        texture_data = np.asarray(self._texture_buffer.data)
        point_count = int(gl_value.shape[0])
        texture_count = int(texture_data.shape[0]) if texture_data.ndim > 0 else 0
        if texture_count != point_count:
            self._texture_buffer.data = np.zeros((point_count, 1), dtype=np.float32)

    @property
    def texture_index(self) -> NDArray[np.floating]:
        """
        Get the array of texture indices.

        This property returns the array of texture indices that determine which
        texture from the texture array is used for each point. Each index corresponds
        to a point in the points array. Stored as float32 in the GL buffer.
        Values: 0 idle, 1 selected blink, 2 busy (grey glyph + comet in the shader).

        Returns:
            NDArray[np.floating]: Array of texture indices (stored as float32 in GL buffer)
        """
        return self._texture_buffer.data  # type: ignore[return-value]

    @texture_index.setter
    def texture_index(self, value: NDArray[np.floating]):
        """
        Set the array of texture indices.

        This setter allows changing the texture indices used for rendering each point.
        The input array is converted to float32 for compatibility with the OpenGL buffer.

        Args:
            value (NDArray[np.floating]): New array of texture indices
        """
        value = value.get() if hasattr(value, "get") else value  # type: ignore[attr-defined]
        value = np.asarray(value, dtype=np.float32)
        self._texture_buffer.data = value

    # Verticies for a square centered at the origin, the last two columns are texture coordinates
    _square_verts: NDArray[np.floating] = np.array([[-0.5, -0.5, 0.0, 0.0, 0.0],
                                                    [0.5, -0.5, 0.0, 1.0, 0.0],
                                                    [0.5, 0.5, 0.0, 1.0, 1.0],
                                                    [-0.5, 0.5, 0.0, 0, 1.0]], dtype=np.float32)

    _indicies: NDArray[np.uint16] = np.array([0, 1, 2, 2, 3, 0], dtype=np.uint16)

    def __init__(self,
                 points: NDArray[np.floating] | GLBuffer | None,
                 texture_indicies: NDArray[np.integer] | GLIndexBuffer | None,
                 texture_array: int,
                 gl_funcs: QOpenGLFunctions | None = None):
        """
        Initialize a new PointView.

        Creates a new PointView for rendering a set of points with textures.
        The points can be provided as a NumPy array or as a pre-existing GLBuffer.
        Similarly, the texture indices can be provided as a NumPy array or as a
        pre-existing GLIndexBuffer.

        Args:
            points (NDArray[np.floating] | GLBuffer | None): Control point locations.
                If provided as a NumPy array, should be in the format Nx4 with columns
                representing SourceY, SourceX, TargetY, TargetX. If None, an empty
                point set is created.
            texture_indicies (NDArray[np.integer] | GLIndexBuffer | None): Indices of
                textures to use for each point. If None, all points use texture 0.
            texture_array (int): OpenGL texture array ID containing the textures to use.
            gl_funcs (QOpenGLFunctions | None, optional): OpenGL functions to use.
                If None, a new QOpenGLFunctions object will be created when needed.
                
        Raises:
            RuntimeError: If no valid OpenGL context is current when creating OpenGL objects
        """
        # Validate that we have an active OpenGL context
        from PyQt6.QtGui import QOpenGLContext
        context = QOpenGLContext.currentContext()
        if not context or not context.isValid():
            raise RuntimeError("PointView.__init__ requires an active OpenGL context. "
                             "Ensure the context is current before creating PointView objects.")
        
        self._gl_funcs = gl_funcs
        self.create_open_gl_objects(pyre.gl_engine.shaders.controlpointset_shader, points,  # type: ignore[attr-defined]
                                    texture_indicies=texture_indicies)  # type: ignore[arg-type]
        self._texture_array = texture_array
        self._num_textures = get_texture_array_length(texture_array)
        self.validate_texture_indicies(texture_indicies)  # type: ignore[arg-type]

    def validate_texture_indicies(self, texture_indicies: NDArray[np.integer] | GLBuffer | None):
        """
        Validate that the texture indices are within the bounds of the texture array.

        This method checks that all texture indices are valid for the current texture array.
        Valid indices must be non-negative and less than the number of textures in the array.

        Args:
            texture_indicies (NDArray[np.integer] | GLBuffer | None): Indices of
                textures to use for each point. If None or an empty buffer, no validation
                is performed.

        Raises:
            ValueError: If any texture index is negative or greater than or equal to
                       the number of textures in the texture array
        """
        if texture_indicies is None:
            return

        if isinstance(texture_indicies, GLBuffer):
            if texture_indicies.capacity == 0:  # If we are not setting any texture indicies there is nothing to check
                return

            texture_indicies = texture_indicies.data  # type: ignore[assignment]

        if max(texture_indicies) >= self._num_textures:  # type: ignore[arg-type]
            raise ValueError(
                "Array of texture indicies contains values larger than the number of textures in texture array")
        elif min(texture_indicies) < 0:  # type: ignore[arg-type]
            raise ValueError("Array of texture indicies contains negative values")

    def create_open_gl_objects(self,
                               shader: ControlPointSetShader,
                               points: NDArray[np.floating] | GLBuffer | None = None,
                               texture_indicies: NDArray[np.integer] | GLBuffer | None = None):
        """
        Create the OpenGL objects needed for rendering.

        This method initializes all the OpenGL resources needed for rendering the points,
        including buffers and the vertex array object (VAO). It first populates the buffers
        with the provided data and then creates the VAO to organize the buffers for rendering.

        Args:
            shader (ControlPointSetShader): The shader program to use for rendering
            points (NDArray[np.floating] | GLBuffer | None, optional): Control point locations.
                If None, an empty point set is created.
            texture_indicies (NDArray[np.integer] | GLBuffer | None, optional): Indices of
                textures to use for each point. If None, all points use texture 0.
        """
        self._populate_buffers(shader, points, texture_indicies)
        self._create_vao()

    def _populate_buffers(self, shader: ControlPointSetShader,
                          points: NDArray[np.floating] | GLBuffer | None = None,
                          texture_indicies: NDArray[np.integer] | GLBuffer | None = None):
        """
        Create and populate the OpenGL buffers for rendering.

        This internal method creates the vertex buffer, point buffer, and texture index buffer
        needed for rendering. If the buffers already exist, it updates them with the new data.

        The method handles both NumPy arrays and pre-existing GLBuffer objects for points
        and texture indices. If points are provided as a NumPy array, they are transformed
        to match the OpenGL coordinate system.

        Args:
            shader (ControlPointSetShader): The shader program to use for rendering
            points (NDArray[np.floating] | GLBuffer | None, optional): Control point locations.
                If None, an empty point set is created.
            texture_indicies (NDArray[np.integer] | GLBuffer | None, optional): Indices of
                textures to use for each point. If None, all points use texture 0.
        """
        self._vertex_buffer = GLBuffer(layout=shader.vertex_layout, data=self._square_verts, usage=gl.GL_STATIC_DRAW)
        if points is None:
            points = np.zeros((0, 3), dtype=np.float32)
        if isinstance(points, np.ndarray):
            # Swap the point order
            points = TransformController.swap_columns_to_XY(points)
            self._point_buffer = GLBuffer(layout=shader.pointset_layout, data=points, usage=gl.GL_DYNAMIC_DRAW)
        else:
            self._point_buffer = points  # Points is already a GLBuffer

        if texture_indicies is None:
            texture_indicies = np.zeros((len(points), 1), dtype=np.float32)  # type: ignore[arg-type]
        if isinstance(texture_indicies, np.ndarray):
            self._texture_buffer = GLBuffer(layout=shader.texture_index_layout,
                                            data=texture_indicies, usage=gl.GL_DYNAMIC_DRAW)  # type: ignore[arg-type]
        else:
            self._texture_buffer = texture_indicies  # type: ignore[assignment]

    def _create_vao(self):
        """
        Create the Vertex Array Object (VAO) for rendering.

        This internal method creates an InstancedVAO and configures it with the
        point buffer, texture buffer, vertex buffer, and index buffer. The VAO
        organizes these buffers for efficient rendering with the shader program.

        The VAO is initialized following the multi-step process required by the
        InstancedVAO class: begin_init(), add buffers, add index buffer, and end_init().
        """

        self._vao = InstancedVAO()

        self._vao.begin_init()
        self._vao.add_buffer(self._point_buffer)
        self._vao.add_buffer(self._texture_buffer)
        assert self._vertex_buffer is not None
        self._vao.add_buffer(self._vertex_buffer)
        self._vao.add_index_buffer(self._indicies)
        self._vao.end_init()

    def draw(self, view_proj_matrix: NDArray[np.floating], tween: float, scale_factor: float,
             busy_angle: float = 0.0):
        """
        Render the points with their associated textures.

        This method renders all points in the point buffer as textured quads (billboards)
        using the shader program. It configures OpenGL state for proper blending,
        binds the VAO, and invokes the shader to draw the points.

        Args:
            view_proj_matrix (NDArray[np.floating]): The combined view and projection matrix
                for transforming the points to screen space
            tween (float): Interpolation factor for animations, typically between 0.0 and 1.0
            scale_factor (float): Scale factor to apply to the point billboards, controlling
                their size on screen
            busy_angle (float): Spin angle in radians for the busy comet arc
        """
        from pyre.gl_engine.helpers import check_for_error
        self.gl_funcs.glDisable(gl.GL_DEPTH_TEST)
        check_for_error("after glDisable(GL_DEPTH_TEST) in pointview.draw")
        self.gl_funcs.glEnable(gl.GL_BLEND)
        check_for_error("after glEnable(GL_BLEND) in pointview.draw")
        self.gl_funcs.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
        check_for_error("after glBlendFunc in pointview.draw")
        pyre.gl_engine.shaders.controlpointset_shader.draw(view_proj_matrix,  # type: ignore[attr-defined]
                                                           self._texture_array,
                                                           self._vao,
                                                           len(self._point_buffer.data),  # type: ignore[arg-type]
                                                           tween=tween, scale=scale_factor,
                                                           busy_angle=busy_angle)
        self.gl_funcs.glEnable(gl.GL_DEPTH_TEST)
        check_for_error("after glEnable(GL_DEPTH_TEST) in pointview.draw")
