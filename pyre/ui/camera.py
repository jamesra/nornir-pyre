"""
Created on Oct 17, 2012

@author: u0490822
"""

import math

import nornir_imageregistration
import numpy as np
from numpy.typing import NDArray

import pyre


def screen_to_volume(camera, point):
    camera.ImageCoordsForMouse(point)


class Camera:
    """
    classdocs
    """

    _projection: NDArray[np.floating]
    _view: NDArray[np.floating]
    _view_proj: NDArray[np.floating]

    @property
    def x(self) -> float:
        """Position in volume space"""
        return self._lookat[nornir_imageregistration.iPoint.X]

    @property
    def y(self) -> float:
        """Position in volume space"""
        return self._lookat[nornir_imageregistration.iPoint.Y]

    @property
    def WindowSize(self) -> tuple[int, int]:
        return self._window_size

    @WindowSize.setter
    def WindowSize(self, value: tuple[int, int]):
        # print("Update window size: %d x %d" % (value[1], value[0]))
        self._window_size = np.array(value)
        self._aspect = float(self._window_size[nornir_imageregistration.iPoint.X]) / float(
            self._window_size[nornir_imageregistration.iPoint.Y])
        self._view_size = Camera._Calc_ViewSize(self.scale, self.Aspect)

    @property
    def Aspect(self) -> float:
        return self._aspect

    @property
    def WindowWidth(self) -> int:
        return self._window_size[nornir_imageregistration.iPoint.X]

    @property
    def WindowHeight(self) -> int:
        return self._window_size[nornir_imageregistration.iPoint.Y]

    @property
    def VisibleImageWidth(self) -> float:
        return self._window_size[nornir_imageregistration.iPoint.X] * self.scale

    @property
    def VisibleImageHeight(self) -> float:
        return self._window_size[nornir_imageregistration.iPoint.Y] * self.scale

    @classmethod
    def _Calc_ViewSize(cls, scale: float, aspect: float):
        return np.array((scale, aspect * scale))

    @property
    def ViewSize(self):
        return self._view_size

    @property
    def ViewWidth(self) -> float:
        """Visible volume width"""
        return self._view_size[nornir_imageregistration.iPoint.X]

    @property
    def ViewHeight(self) -> float:
        """Visible volume height"""
        return self._view_size[nornir_imageregistration.iPoint.Y]

    @property
    def angle(self) -> float:
        return self._angle

    @angle.setter
    def angle(self, value: float):
        self._angle = float(value)
        self._FireChangeEvent()

    @property
    def scale(self) -> float:
        return self._scale

    @scale.setter
    def scale(self, value: float):
        self._scale = float(value)
        self._view_size = Camera._Calc_ViewSize(self.scale, self.Aspect)
        self._FireChangeEvent()

    def ImageCoordsForMouse(self, y: float, x: float) -> tuple[float, float]:
        ImageX = ((float(x) / self.WindowWidth) * self.ViewWidth) + (self.x - (self.ViewWidth / 2.0))
        ImageY = ((float(y) / self.WindowHeight) * self.ViewHeight) + (self.y - (self.ViewHeight / 2.0))
        return ImageY, ImageX

    @property
    def VisibleImageBoundingBox(self) -> nornir_imageregistration.Rectangle:
        (bottom, left) = self.ImageCoordsForMouse(0, 0)
        (top, right) = self.ImageCoordsForMouse(self.WindowHeight, self.WindowWidth)

        return nornir_imageregistration.Rectangle.CreateFromBounds(np.array((bottom, left, top, right)))

    def __init__(self, position: nornir_imageregistration.PointLike, scale=1, angle=0, size=None):
        """
        :param tuple size: Size of the window the camera is within

        """
        self._lookat = nornir_imageregistration.EnsurePointsAre1DNumpyArray(position)  # centered on
        self._angle = 0  # tilt
        self._scale = scale  # zoom
        self.__OnChangeEventListeners = []
        self._aspect = None

        if size is None:
            self.WindowSize = np.array((480, 640))
        else:
            self.WindowSize = np.array(size)

    def AddOnChangeEventListener(self, func):
        self.__OnChangeEventListeners.append(func)

    def RemoveOnChangeEventListener(self, func):
        if func in self.__OnChangeEventListeners:
            self.__OnChangeEventListeners.remove(func)

    def _FireChangeEvent(self):
        for func in self.__OnChangeEventListeners:
            func()

    @property
    def lookat(self) -> NDArray[float]:
        return np.copy(self._lookat)

    @lookat.setter
    def lookat(self, point: nornir_imageregistration.PointLike):
        """:param tuple point: (y,x)
           :param float scale: scale
        """
        self._lookat = np.array(point, dtype=float)
        # self._scale = scale

        # print("X: %g Y: %g S: %g" % (self.x, self.y, self.scale))

        self._FireChangeEvent()

    @property
    def projection(self) -> NDArray[np.floating]:
        """projection matrix"""
        return self._projection

    @property
    def view(self) -> NDArray[np.floating]:
        """View matrix"""
        return self._view

    @property
    def view_proj(self) -> NDArray[np.floating]:
        """View projection matrix"""
        return self._view_proj

    def focus(self, win_width: int, win_height: int):

        self.WindowSize = (win_height, win_width)

        aspect = self.Aspect

        scale = self.scale / 2.0

        # self._projection = Mat4.orthogonal_projection(
        #     -scale * aspect, scale * aspect, -scale, scale, -255, 255
        # )

        self._projection = self.orthogonal_projection(-scale * aspect, scale * aspect, -scale, scale, -1, 1)

        self._view = self.look_at(position=np.array((self.x, self.y, +1.0)),
                                  target=np.array((self.x, self.y, -1.0)),
                                  up=np.array((0, 1, 0)))  # camera  x,y,z

        self._view_proj = self._projection @ self._view

    @classmethod
    def orthogonal_projection(cls: NDArray[np.floating], left: float, right: float, bottom: float, top: float,
                              z_near: float, z_far: float) -> NDArray[np.floating]:
        """Create a Mat4 orthographic projection matrix for use with OpenGL.

        Given left, right, bottom, top values, and near/far z planes,
        create a 4x4 Projection Matrix. This is useful for setting
        :py:attr:`~pyglet.window.Window.projection`.
        """
        width = right - left
        height = top - bottom
        depth = z_far - z_near

        sx = 2.0 / width
        sy = 2.0 / height
        sz = 2.0 / -depth

        tx = -(right + left) / width
        ty = -(top + bottom) / height
        tz = -(z_far + z_near) / depth

        return np.array(((sx, 0.0, 0.0, 0.0),
                         (0.0, sy, 0.0, 0.0),
                         (0.0, 0.0, sz, 0.0),
                         (tx, ty, tz, 1.0)),
                        dtype=np.float32)

    @staticmethod
    def normalize(vec: NDArray[np.floating], axis=-1, order=2):
        """Normalize a vector"""
        l2 = np.atleast_1d(np.linalg.norm(vec, order, axis))
        l2[l2 == 0] = 1
        return vec / np.expand_dims(l2, axis)

    @classmethod
    def look_at(cls, position: NDArray[np.floating], target: NDArray[np.floating], up: NDArray[np.floating]) -> NDArray[
        np.floating]:
        f = cls.normalize(target - position)
        u = cls.normalize(up)
        s = cls.normalize(np.cross(f, u))
        u = np.cross(s, f)

        f = f.flatten()
        u = u.flatten()
        s = s.flatten()

        return np.array(((s[0], u[0], -f[0], 0.0),
                         (s[1], u[1], -f[1], 0.0),
                         (s[2], u[2], -f[2], 0.0),
                         (-s.dot(position), -u.dot(position), f.dot(position), 1.0)))
