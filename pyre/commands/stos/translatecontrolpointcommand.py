from __future__ import annotations

from dependency_injector.wiring import inject, Provide
import numpy as np
from numpy._typing import NDArray
import wx

import nornir_imageregistration
import pyre
from pyre.observable import ObservableSet, ObservedAction
from pyre import Space
from pyre.command_interfaces import StatusChangeCallback
from pyre.commands import NavigationCommandBase
from pyre.commands.commandexceptions import RequiresSelectionError
from pyre.interfaces.managers import ICommandQueue, IMousePositionHistoryManager
from pyre.container import IContainer


class TranslateControlPointCommand(NavigationCommandBase):
    """This command takes a selection of control points and adjusts the position"""

    _selected_point_set: ObservableSet[int]  # The indices of the selected points
    _command_points: set[int]  # Points under mouse when command was triggered
    _space: Space
    _translate_origin: NDArray[float, float]
    _original_points: NDArray[[2, ], np.floating]

    _mouse_position_history: IMousePositionHistoryManager = Provide[IContainer.mouse_position_history]

    @property
    def translated_points(self) -> NDArray[[2, ], np.floating]:
        return self._transform_controller.points[self._selected_point_set]

    @inject
    def __init__(self,
                 parent: wx.Window,
                 camera: pyre.ui.Camera,
                 bounds: nornir_imageregistration.Rectangle,
                 selected_points: ObservableSet[int],  # The indices of the selected points
                 command_points: set[int],  # Points under mouse when command was triggered
                 space: Space,  # Space we are moving the points in, source or target side
                 commandqueue: ICommandQueue,
                 translate_all: bool = False,  # True if all points in the transform should be translated
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
        self._selected_point_set = selected_points

        if translate_all:
            self._command_points = set(range(transform_controller.NumPoints))
        else:
            combined_command_points = set(selected_points)
            combined_command_points.update(command_points)
            self._command_points = combined_command_points

        if len(self._command_points) == 0:
            raise RequiresSelectionError()

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

        new_selected_indicies = self._transform_controller.MovePoint(self._selected_point_set, delta[1], delta[0],
                                                                     space=self.space)

        # Update selected points in the UI if indicies have changed
        if len(set(new_selected_indicies) - self._selected_point_set) > 0:
            self._selected_point_set.clear()
            self._selected_point_set.update(new_selected_indicies)

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

            self._transform_controller.MovePoint(self._selected_point_set, delta[1], delta[0],
                                                 space=self._space)
        return

    def activate(self):
        super().activate()
        self._selected_point_set.update(
            self._command_points)  # Ensure the command points are included in the selected points

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
