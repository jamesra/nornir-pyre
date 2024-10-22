"""
Created on Oct 17, 2012

@author: u0490822
"""

import logging
from typing import Callable

import numpy as np
from numpy.typing import NDArray

import nornir_imageregistration
from dependency_injector.wiring import Provide
from pyre.container import IContainer
from pyre.interfaces.readonlycamera import IReadOnlyCamera


def screen_to_volume(camera, point):
    camera.ImageCoordsForMouse(point)


class Camera(IReadOnlyCamera):
    """
    classdocs
    """

    config = Provide[IContainer.config]

    _projection: NDArray[np.floating]
    _view: NDArray[np.floating]
    _view_proj: NDArray[np.floating]
    __on_change_event_listeners: list[Callable[[], None]]
    _angle: float
    _scale: float
    _lookat: NDArray[float]
    _log: logging.Logger
    _window_size: NDArray[int]
    _view_size: NDArray[float]

    @property
    def max_zoom(self) -> float:
        return self.config['max_zoom']

    @property
    def min_zoom(self) -> float:
        return self.config['min_zoom']

    @property
    def x(self) -> float:
        """Position in volume space"""
        return float(self._lookat[nornir_imageregistration.iPoint.X])

    @property
    def y(self) -> float:
        """Position in volume space"""
        return float(self._lookat[nornir_imageregistration.iPoint.Y])

    @property
    def window_size(self) -> tuple[int, int]:
        return self._window_size

    @window_size.setter
    def window_size(self, value: tuple[int, int]):
        "Sets the size of the window the camera is within"
        # print("Update window size: %d x %d" % (value[1], value[0]))
        if self._window_size[0] == value[0] and self._window_size[1] == value[1]:
            return

        self._window_size = np.array(value)
        self._aspect = float(self._window_size[nornir_imageregistration.iPoint.X]) / float(
            self._window_size[nornir_imageregistration.iPoint.Y])
        self._view_size = self._calc_view_size(self.scale, self.aspect)

    @property
    def aspect(self) -> float:
        return self._aspect

    @property
    def WindowWidth(self) -> int:
        return int(self._window_size[nornir_imageregistration.iPoint.X])

    @property
    def WindowHeight(self) -> int:
        return int(self._window_size[nornir_imageregistration.iPoint.Y])

    def _calc_view_size(self, scale: float, aspect: float) -> NDArray[float]:
        """Calculate the size of the visible world based on the scale"""
        size = self._window_size[0] / scale
        return np.array((size, aspect * size))

    @property
    def visible_world_size(self) -> NDArray[float]:
        return self._view_size

    @property
    def visible_world_width(self) -> float:
        """Visible volume width"""
        return float(self._view_size[nornir_imageregistration.iPoint.X])

    @property
    def visible_world_height(self) -> float:
        """Visible volume height"""
        return float(self._view_size[nornir_imageregistration.iPoint.Y])

    @property
    def angle(self) -> float:
        """Angle of rotation in radians"""
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

        if value > self.max_zoom:
            value = self.max_zoom
        elif value < self.min_zoom:
            value = self.min_zoom

        self._scale = float(value)
        self._view_size = self._calc_view_size(self.scale, self.aspect)
        self._FireChangeEvent()

    def top_left_visible_world_coords(self):
        """Coordinates of the top left corner of the visible world"""
        return self.lookat - (self.visible_world_size / 2.0)

    def ImageCoordsForMouse(self, y: float, x: float) -> NDArray[np.floating]:
        """Convert a mouse position on the screen to a position in the world"""

        offset = np.array((y, x), dtype=float)
        offset = (offset / self._window_size) * self.visible_world_size
        world_coords = self.top_left_visible_world_coords() + offset
        return world_coords

        # image_x = ((float(x) / self.WindowWidth) * self.visible_world_width) + (
        #         self.x - (self.visible_world_width / 2.0))
        # image_y = ((float(y) / self.WindowHeight) * self.visible_world_height) + (
        #         self.y - (self.visible_world_height / 2.0))
        # return image_y, image_x

    @property
    def VisibleImageBoundingBox(self) -> nornir_imageregistration.Rectangle:
        (bottom, left) = self.ImageCoordsForMouse(0, 0)
        (top, right) = self.ImageCoordsForMouse(self.WindowHeight, self.WindowWidth)

        return nornir_imageregistration.Rectangle.CreateFromBounds(np.array((bottom, left, top, right)))

    def __init__(self, position: nornir_imageregistration.PointLike, scale=1, angle=0, size=None,
                 log: logging.Logger = logging.getLogger("camera")):
        """
        :param tuple size: Size of the window the camera is within

        """
        self._log = log
        self._lookat = nornir_imageregistration.EnsurePointsAre1DNumpyArray(position)  # centered on
        self._angle = 0  # tilt
        self._scale = scale  # zoom
        self.__OnChangeEventListeners = []
        self._aspect = None
        self._window_size = np.array((1, 1))

        if size is None:
            self.window_size = np.array((480, 640))
        else:
            self.window_size = np.array(size)

    def AddOnChangeEventListener(self, func: Callable[[], None]):
        self.__OnChangeEventListeners.append(func)

    def RemoveOnChangeEventListener(self, func: Callable[[], None]):
        if func in self.__OnChangeEventListeners:
            self.__OnChangeEventListeners.remove(func)

    def _FireChangeEvent(self):
        for func in self.__OnChangeEventListeners:
            func()

    def translate(self, delta: nornir_imageregistration.PointLike):
        """translate the camera by the specified amount"""
        # print("Translate X: %g Y: %g" % (delta[1], delta[0]))
        delta = nornir_imageregistration.EnsureArray(delta, float)
        self.lookat += delta

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

        aspect = self.aspect

        half_window_size = (np.array(self.window_size) / self.scale) / 2.0

        if aspect == 0:
            self._log.warn("No aspect ratio in camera.focus")
            return

        # self._projection = Mat4.orthogonal_projection(
        #     -scale * aspect, scale * aspect, -scale, scale, -255, 255
        # )

        self._projection = self.orthogonal_projection(-half_window_size[1], half_window_size[1],
                                                      -half_window_size[0], half_window_size[0],
                                                      -255, 255)

        self._view = self.look_at(position=np.array((self.x, self.y, +1.0)),
                                  target=np.array((self.x, self.y, -1.0)),
                                  up=np.array((0, 1, 0)))  # camera  x,y,z

        # self._view_proj = self._projection @ self._view
        self._view_proj = self._view @ self._projection

    @classmethod
    def orthogonal_projection(cls: NDArray[np.floating], left: float, right: float, bottom: float, top: float,
                              z_near: float, z_far: float) -> NDArray[np.floating]:
        """Create a Mat4 orthographic projection matrix for use with OpenGL.

        Given left, right, bottom, top values, and near/far z planes,
        create a 4x4 Projection Matrix.
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

        return np.array(((sx, 0, 0, tx),
                         (0, sy, 0, ty),
                         (0, 0, sz, tz),
                         (0, 0, 0, 1.0)),
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
