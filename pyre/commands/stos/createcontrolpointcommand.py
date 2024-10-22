from __future__ import annotations

from dependency_injector.wiring import inject, Provide
import numpy as np
from numpy.typing import NDArray
import wx

import nornir_imageregistration
import pyre
from pyre import Space
from pyre.command_interfaces import StatusChangeCallback, ICommand
from pyre.commands import NavigationCommandBase
from pyre.interfaces.managers import ICommandQueue, IMousePositionHistoryManager
from pyre.container import IContainer
from pyre.selection_event_data import InputEvent, InputModifiers, SelectionEventData, InputSource, PointPair


class CreateControlPointCommand(NavigationCommandBase):
    """This command deletes a selection of control points"""

    _space: Space
    _new_point_position: PointPair

    _mouse_position_history: IMousePositionHistoryManager = Provide[IContainer.mouse_position_history]
    _original_points: NDArray[np.floating]
    _left_mouse_down: bool = False

    @inject
    def __init__(self,
                 parent: wx.Window,
                 camera: pyre.ui.Camera,
                 bounds: nornir_imageregistration.Rectangle,
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
        source_position = self._mouse_position_history[Space.Source]
        target_position = self._mouse_position_history[Space.Target]
        self._left_mouse_down = True
        self._new_point_position = PointPair(source=source_position, target=target_position)
        self._original_points = transform_controller.points

    def on_activate(self):
        wx.CallAfter(self.queue_translate_command)

    def __str__(self):
        return "CreateControlPointCommand"

    def on_mouse_press(self, event: wx.MouseEvent):
        """Called when the mouse is pressed"""
        self._left_mouse_down = event.LeftIsDown()
        super().on_mouse_press(event)

    def on_mouse_release(self, event: wx.MouseEvent):
        """Called when the mouse is released"""
        self._left_mouse_down = event.LeftIsDown()
        super().on_mouse_release(event)

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
        super().on_key_up(event)

    def can_execute(self) -> bool:
        return True

    def cancel(self):
        super().cancel()
        return

    def queue_translate_command(self):

        point = self._new_point_position
        # point = self._new_point_position.source if self.space == Space.Source else self._new_point_position.target
        newpoint = np.array([point.target[0], point.target[1], point.source[0], point.source[1]], dtype=np.float32)
        index = self._transform_controller.TransformModel.AddPoint(newpoint)

        # Queue up a translate command to move the point to the new position if the LMB is still down
        if self._left_mouse_down:
            translate_command = pyre.commands.stos.TranslateControlPointCommand(parent=self.parent,
                                                                                transform_controller=self._transform_controller,
                                                                                camera=self.camera,
                                                                                bounds=self._bounds,
                                                                                space=self.space,
                                                                                commandqueue=self._commandqueue,
                                                                                selected_points=[index],
                                                                                completed_func=self.check_for_cancel)
            self._commandqueue.put(translate_command)
            self.deactivate()
            return
        else:
            self.execute()

    def check_for_cancel(self, translate_command: ICommand):
        # Undo the addition of the translation was cancelled
        if translate_command.status == pyre.CommandStatus.Completed and \
                translate_command.result != pyre.CommandResult.Executed:
            self._transform_controller.SetPoints(self._original_points)
            super().cancel()
            return
        else:
            self.execute()
            return

    def subscribe_to_parent(self):
        self._bind_mouse_events()
        self._bind_key_events()

    def unsubscribe_to_parent(self):
        self._unbind_mouse_events()
        self._unbind_key_events()
