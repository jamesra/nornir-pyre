"""
A class that stores a set of points and renders a texture centered on each point
"""
import OpenGL.GL as gl
import numpy as np
from numpy.typing import NDArray

import pyre
from pyre.controllers import TransformController
from pyre.gl_engine import GLBuffer, GLIndexBuffer, InstancedVAO, get_texture_array_length
from pyre.gl_engine.shaders import ControlPointSetShader


class PointView:
    """
    Contains all of the information required to render a set of points in open GL with instanced billboard textures
    """
    _texture_array: int  # The texture array
    _vertex_buffer: GLBuffer | None  # A single vertex array represents all points.  We scale the model matrix to render.
    _point_buffer: GLBuffer  # The points to render
    _texture_buffer: GLBuffer  # The texture index for each point
    _vao: InstancedVAO  # The vertex array object

    _num_textures: int  # The number of textures in the texture array

    @property
    def num_textures(self) -> int:
        """The number of textures in the texture array"""
        return self._num_textures

    @property
    def texture(self) -> int:
        """The texture to render"""
        return self._texture_array

    @texture.setter
    def texture(self, value: int):
        """Change the texture to render"""
        self._texture_array = value

    @property
    def points(self) -> NDArray[np.floating]:
        """The points to render"""
        return self._point_buffer.data

    @points.setter
    def points(self, value: NDArray[np.floating]):
        """Change the points to render"""
        value = value.astype(dtype=np.float32, copy=False)
        gl_value = TransformController.swap_columns_to_XY(value)
        self._point_buffer.data = gl_value

    @property
    def texture_index(self) -> NDArray[np.integer]:
        """
        The index of the texture to use for each control point
        """
        return self._texture_buffer.data

    @texture_index.setter
    def texture_index(self, value: NDArray[np.integer]):
        """
        The index of the texture to use for each control point
        """
        value = value.astype(dtype=np.float32, copy=False)
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
                 texture_array: int):
        """
        :param points: Control point locations Nx4, SourceY, SourceX, TargetY, TargetX
        :param texture_indicies: Index of the texture to use for each point
        :param texture_array: Texture array
        """
        self.create_open_gl_objects(pyre.gl_engine.shaders.controlpointset_shader, points,
                                    texture_indicies=texture_indicies)
        self._texture_array = texture_array
        self._num_textures = get_texture_array_length(texture_array)
        self.validate_texture_indicies(texture_indicies)

    def validate_texture_indicies(self, texture_indicies: NDArray[np.integer] | GLBuffer | None):
        """
        Validate that the texture indicies are within the bounds of the texture array
        :param texture_indicies: Index of the texture to use for each point
        """
        if texture_indicies is None:
            return

        if isinstance(texture_indicies, GLBuffer):
            texture_indicies = texture_indicies.data

        if max(texture_indicies) >= self._num_textures:
            raise ValueError(
                "Array of texture indicies contains values larger than the number of textures in texture array")
        elif min(texture_indicies) < 0:
            raise ValueError("Array of texture indicies contains negative values")

    def create_open_gl_objects(self,
                               shader: ControlPointSetShader,
                               points: NDArray[np.floating] | GLBuffer | None = None,
                               texture_indicies: NDArray[np.integer] | GLBuffer | None = None):
        self._populate_buffers(shader, points, texture_indicies)
        self._create_vao()

    def _populate_buffers(self, shader: ControlPointSetShader,
                          points: NDArray[np.floating] | GLBuffer | None = None,
                          texture_indicies: NDArray[np.integer] | GLBuffer | None = None):
        """Creates buffers if they do not exist, otherwise points to existing buffers"""
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
            texture_indicies = np.zeros(len(points), dtype=np.uint16)
        if isinstance(texture_indicies, np.ndarray):
            self._texture_buffer = GLBuffer(layout=shader.texture_index_layout,
                                            data=texture_indicies, usage=gl.GL_DYNAMIC_DRAW)
        else:
            self._texture_buffer = texture_indicies  # Texture index is already a GLBuffer

    def _create_vao(self):
        """
        Create the VAO.
        """

        self._vao = InstancedVAO()

        self._vao.begin_init()
        self._vao.add_buffer(self._point_buffer)
        self._vao.add_buffer(self._texture_buffer)
        self._vao.add_buffer(self._vertex_buffer)
        self._vao.add_index_buffer(self._indicies)
        self._vao.end_init()

    def draw(self, view_proj_matrix: NDArray[np.floating], tween: float, scale_factor: float):
        """Draw the points"""
        gl.glDisable(gl.GL_DEPTH_TEST)
        gl.glEnable(gl.GL_BLEND)
        gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
        pyre.gl_engine.shaders.controlpointset_shader.draw(view_proj_matrix,
                                                           self._texture_array,
                                                           self._vao,
                                                           len(self._point_buffer.data),
                                                           tween=tween, scale=scale_factor)
        gl.glEnable(gl.GL_DEPTH_TEST)
