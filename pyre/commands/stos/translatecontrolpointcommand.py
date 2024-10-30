from __future__ import annotations

from dependency_injector.wiring import inject, Provide
import numpy as np
from numpy._typing import NDArray
import wx

import nornir_imageregistration
import pyre
from pyre import Space
from pyre.command_interfaces import StatusChangeCallback
from pyre.commands import NavigationCommandBase
from pyre.interfaces.managers import ICommandQueue, IMousePositionHistoryManager
from pyre.container import IContainer


class TranslateControlPointCommand(NavigationCommandBase):
    """This command takes a selection of control points and adjusts the position"""

    _selected_points: list[int]  # The indices of the selected points
    _space: Space
    _translate_origin: NDArray[float, float]
    _original_points: NDArray[[2, ], np.floating]

    _mouse_position_history: IMousePositionHistoryManager = Provide[IContainer.mouse_position_history]

    @property
    def translated_points(self) -> NDArray[[2, ], np.floating]:
        return self._transform_controller.points[self._selected_points]

    @inject
    def __init__(self,
                 parent: wx.Window,
                 camera: pyre.ui.Camera,
                 bounds: nornir_imageregistration.Rectangle,
                 selected_points: list[int],  # The indices of the selected points
                 space: Space,  # Space we are moving the points in, source or target side
                 commandqueue: ICommandQueue,
                 completed_func: StatusChangeCallback = None,
                 transform_controller: pyre.viewmodels.TransformController = Provide[IContainer.transform_controller],
                 **kwargs):
        """

        :param parent:
        :param transform_controller:
        :param camera:
        :param bounds:
        :param translate_origin:  Where the mouse was when the translation started
        :param selected_points:
        :param space:
        :param completed_func:
        """
        super().__init__(parent, transform_controller=transform_controller,
                         camera=camera, bounds=bounds,
                         space=space, commandqueue=commandqueue,
                         completed_func=completed_func)
        mouse_position = self._mouse_position_history[space]
        self._translate_origin = mouse_position
        self._selected_points = selected_points
        if len(selected_points) == 0 or selected_points is None:
            raise ValueError('No points selected')

        self._original_points = transform_controller.points

    def __str__(self):
        return "TranslateControlPointCommand"

    def on_mouse_press(self, event: wx.MouseEvent):
        """Called when the mouse is pressed"""
        if event.MiddleIsDown() or event.RightIsDown():
            self.cancel()  # Cancel if the middle mouse button is pressed

    def on_mouse_release(self, event: wx.MouseEvent):
        """Called when the mouse is released"""

        if not event.LeftIsDown():
            self.execute()

    def on_mouse_motion(self, event: wx.MouseEvent):
        """Called when the mouse is dragged"""

        if event.RightIsDown():
            # super().on_mouse_motion(event)
            self.cancel()
            return

        if not event.LeftIsDown():
            return

        point_pair = self.get_world_positions(event)

        world_point = point_pair.source if self.space == Space.Source else point_pair.target

        delta = world_point - self._translate_origin
        print(
            f'space: {self.space} x:{world_point[1]} y:{world_point[0]} hx:{self._translate_origin[1]} hy:{self._translate_origin[0]} dx:{delta[1]} dy:{delta[0]}')
        self._translate_origin = world_point

        self._selected_points = self._transform_controller.MovePoint(self._selected_points, delta[1], delta[0],
                                                                     space=self.space)
        pass

    def on_key_down(self, event: wx.KeyEvent):
        """Called when a key is pressed"""
        keycode = event.GetKeyCode()

        if (keycode == wx.WXK_LEFT or
            keycode == wx.WXK_RIGHT or
            keycode == wx.WXK_UP or
            keycode == wx.WXK_DOWN) and self.HighlightedPointIndex is not None:

            # Users can nudge points with the arrow keys.  Holding shift steps five pixels, holding Ctrl shifts 25.  Holding both steps 125
            multiplier = 1
            print(str(multiplier))
            if event.ShiftDown():
                multiplier *= 5
                print(str(multiplier))
            if event.ControlDown():
                multiplier *= 25
                print(str(multiplier))

            delta = [0, 0]
            if keycode == wx.WXK_LEFT:
                delta = [0, -1]
            elif keycode == wx.WXK_RIGHT:
                delta = [0, 1]
            elif keycode == wx.WXK_UP:
                delta = [1, 0]
            elif keycode == wx.WXK_DOWN:
                delta = [-1, 0]

            delta[0] *= multiplier
            delta[1] *= multiplier

            self._transform_controller.MovePoint(self._selected_points, delta[1], delta[0],
                                                 space=self._space)
        elif keycode == wx.WXK_SPACE:

            # If SHIFT is held down, align everything.  Otherwise align the selected point
            if not event.ShiftDown() and self._selected_points is not None:
                self._selected_points = self._transform_controller.AutoAlignPoints(self._selected_points)

            elif event.ShiftDown():
                self._transform_controller.AutoAlignPoints(range(0, self._transform_controller.NumPoints))

            self.history_manager.SaveState(self._transform_controller.SetPoints, self._transform_controller.points)

        return

    def on_mouse_scroll(self, event: wx.MouseEvent):
        """Called when the mouse wheel is scrolled"""
        pass

    def on_key_up(self, event: wx.KeyEvent):
        """Called when a key is released"""
        pass

    def can_execute(self) -> bool:
        return True

    def cancel(self):
        self._transform_controller.SetPoints(self._original_points)
        super().cancel()
        return

    def execute(self):
        # self._transform_controller.points[self._selected_points] = self.translated_points
        super().execute()

    def subscribe_to_parent(self):
        self._bind_mouse_events()
        self._bind_key_events()

    def unsubscribe_to_parent(self):
        self._unbind_mouse_events()
        self._unbind_key_events()
