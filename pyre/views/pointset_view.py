"""
A class that stores a set of points and renders a texture centered on each point
"""
import ctypes
import numpy as np
from numpy.typing import NDArray
import OpenGL.GL as gl
import pyre
import time
from pyre.gl_engine import InstancedVAO, GLBuffer
from pyre.gl_engine.shaders import pointset_shader, PointSetShader


class PointSetView:
    """
    Contains all of the information required to render a set of points in open GL with instanced billboard textures
    """
    _texture: int  # The texture to render
    _vertex_buffer: GLBuffer | None  # A single vertex array represents all points.  We scale the model matrix to render.
    _point_buffer: GLBuffer  # The points to render

    _vao: InstancedVAO  # The vertex array object

    @property
    def texture(self) -> int:
        """The texture to render"""
        return self._texture

    @texture.setter
    def texture(self, value: int):
        """Change the texture to render"""
        self._texture = value

    @property
    def points(self) -> NDArray[np.floating]:
        """The points to render"""
        return self._point_buffer.data

    @points.setter
    def points(self, value: NDArray[np.floating]):
        """Change the points to render"""
        value = value.astype(dtype=np.float32, copy=False)
        gl_value = self.__swap_columns(value)
        self._point_buffer.data = gl_value

    # Verticies for a square centered at the origin, the last two columns are texture coordinates
    _square_verts: NDArray[np.floating] = np.array([[-0.5, -0.5, 0.0, 0.0, 0.0],
                                                    [0.5, -0.5, 0.0, 1.0, 0.0],
                                                    [0.5, 0.5, 0.0, 1.0, 1.0],
                                                    [-0.5, 0.5, 0.0, 0, 1.0]], dtype=np.float32)

    _indicies: NDArray[np.uint16] = np.array([0, 1, 2, 2, 3, 0], dtype=np.uint16)

    def __init__(self, shader: PointSetShader, points: NDArray[np.floating], texture: int):
        self.create_open_gl_objects(shader, points)
        self._texture = texture

    @staticmethod
    def __swap_columns(input: NDArray[np.floating]) -> NDArray[np.floating]:
        """
        OpenGL uses X,Y coordinates.  Everything else in Nornir uses Y,X coordinates in numpy arrays.
        This function swaps the columns in pairs to correctly position points on the screen
        """
        output = input[:, [1, 0, 3, 2]]
        return output

    def create_open_gl_objects(self, shader: PointSetShader, points: NDArray[np.floating]):
        """Create the VAO"""
        self._point_buffer = GLBuffer(layout=shader.pointset_layout, data=points, usage=gl.GL_DYNAMIC_DRAW)
        self._vertex_buffer = GLBuffer(layout=shader.vertex_layout, data=self._square_verts)
        self._vao = InstancedVAO()

        self._vao.begin_init()
        self._vao.add_buffer(self._point_buffer)
        self._vao.add_buffer(self._vertex_buffer)
        self._vao.add_index_buffer(self._indicies)
        self._vao.end_init()

    def draw(self, view_proj_matrix: NDArray[np.floating], tween: float):
        """Draw the points"""
        pyre.gl_engine.shaders.pointset_shader.draw(view_proj_matrix, self._texture, self._vao,
                                                    len(self._point_buffer.data), tween)
