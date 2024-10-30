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
from pyre.interfaces.controlpointselection import SetSelectionCallable
from pyre.container import IContainer


class DeleteControlPointCommand(NavigationCommandBase):
    """This command deletes a selection of control points"""

    _selected_points: list[int]  # The indices of the selected points
    _space: Space
    _translate_origin: NDArray[float, float]
    _original_points: NDArray[[2, ], np.floating]

    _mouse_position_history: IMousePositionHistoryManager = Provide[IContainer.mouse_position_history]
    _set_selection: SetSelectionCallable

    @inject
    def __init__(self,
                 parent: wx.Window,
                 camera: pyre.ui.Camera,
                 bounds: nornir_imageregistration.Rectangle,
                 selected_points: list[int],  # The indices of the selected points
                 space: Space,  # Space we are moving the points in, source or target side
                 set_selection: SetSelectionCallable,
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
        self._set_selection = set_selection
        self._selected_points = selected_points
        if len(selected_points) == 0:
            raise ValueError('No points selected')

        self._original_points = transform_controller.points

    def __str__(self):
        return "DeleteControlPointCommand"

    def on_mouse_press(self, event: wx.MouseEvent):
        """Called when the mouse is pressed"""
        return

    def on_mouse_release(self, event: wx.MouseEvent):
        """Called when the mouse is released"""
        return

    def on_mouse_motion(self, event: wx.MouseEvent):
        """Called when the mouse is dragged"""
        super().on_mouse_motion(event)

    def on_key_down(self, event: wx.KeyEvent):
        """Called when a key is pressed"""
        keycode = event.GetKeyCode()
        if keycode == wx.WXK_SPACE:
            self.cancel()
            # self.history_manager.SaveState(self._transform_controller.SetPoints, self._transform_controller.points)
        else:
            super().on_key_down(event)

        return

    def on_mouse_scroll(self, event: wx.MouseEvent):
        """Called when the mouse wheel is scrolled"""
        super().on_mouse_scroll(event)

    def on_key_up(self, event: wx.KeyEvent):
        """Called when a key is released"""
        return

    def can_execute(self) -> bool:
        return True

    def cancel(self):
        super().cancel()
        return

    def execute(self):
        self._set_selection([])
        self._transform_controller.TryDeletePoints(self._selected_points)
        super().execute()

    def activate(self):
        super().activate()
        self.execute()

    def subscribe_to_parent(self):
        self._bind_mouse_events()
        self._bind_key_events()

    def unsubscribe_to_parent(self):
        self._unbind_mouse_events()
        self._unbind_key_events()
