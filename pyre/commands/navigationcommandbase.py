"""
Created on Feb 10, 2015

@author: u0490822
"""

from __future__ import annotations
import wx
import numpy as np

import nornir_imageregistration
from pyre.commands.commandbase import CommandBase
from pyre.commands.interfaces import CompletionCallback

import pyre.ui

from pyre.ui.camerastatusbar import CameraStatusBar


class NavigationCommandBase(CommandBase):
    """
    A command that needs to handle the mouse position in volume coordinates
    """

    _last_mouse_position = tuple[float, float]
    _statusbar = CameraStatusBar | None
    _transform_controller = pyre.state.TransformController

    # Bounds the camera is allowed to travel within
    _bounds: nornir_imageregistration.Rectangle

    @property
    def camera(self) -> pyre.ui.Camera:
        """The camera used by the command."""
        return self._camera

    def __init__(self,
                 parent: wx.Window,
                 status_bar: CameraStatusBar | None,
                 transform_controller: pyre.viewmodels.TransformController,
                 camera: pyre.ui.Camera,
                 bounds: nornir_imageregistration.Rectangle,
                 completed_func: CompletionCallback | None = None, ):
        """
        :param window parent: Window to subscribe to for events
        :param func completed_func: Function to call when command has completed
        :param Camera camera: Camera to use for mapping screen to volume coordinates
        """
        self._bounds = bounds
        self._statusbar = status_bar
        self._transform_controller = transform_controller
        self._camera = camera
        super(NavigationCommandBase, self).__init__(parent=parent,
                                                    completed_func=completed_func)

    def GetCorrectedMousePosition(self, e: wx.MouseEvent, height: int) -> tuple[float, float]:
        """wxPython inverts the mouse position, flip it back"""
        (x, y) = e.GetPosition()
        return height - y, x

    def on_mouse_motion(self, event: wx.MouseEvent):
        """Called when the mouse moves"""
        width, height = self.parent.GetSize()
        (y, x) = self.GetCorrectedMousePosition(event, height)

        if self._last_mouse_position is None:
            self._last_mouse_position = (y, x)
            return

        dx = x - self._last_mouse_position[nornir_imageregistration.iPoint.X]
        dy = (y - self._last_mouse_position[nornir_imageregistration.iPoint.Y])

        self._last_mouse_position = (y, x)

        ImageY, ImageX = self.camera.ImageCoordsForMouse(y, x)
        if ImageX is None:
            return

        ImageDX = (float(dx) / width) * self.camera.ViewWidth
        ImageDY = (float(dy) / height) * self.camera.ViewHeight

        if self._statusbar is not None:
            self._statusbar.update_status_bar(self._last_mouse_position, in_target_space=self.FixedSpace)

        if event.RightIsDown():
            self.camera.lookat = (self.camera.y - ImageDY, self.camera.x - ImageDX)

        if event.LeftIsDown():
            if event.CmdDown():
                # Translate all points
                self._transform_controller.TranslateFixed((ImageDY, ImageDX))
            else:
                # Create a point or drag a point
                if self.SelectedPointIndex is not None:
                    self.SelectedPointIndex = self._transform_controller.MovePoint(self.SelectedPointIndex, ImageDX,
                                                                                   ImageDY, space=self.space)
                elif event.ShiftDown():  # The shift key is selected and we do not have a last point dragged
                    return
                else:
                    # find nearest point
                    self.SelectedPointIndex = self._transform_controller.TryDrag(ImageX, ImageY, ImageDX, ImageDY,
                                                                                 self.SelectionMaxDistance,
                                                                                 space=self.space)
        self._statusbar.update_status_bar(self._last_mouse_position, in_target_space=self.FixedSpace)

    def on_mouse_scroll(self, e: wx.MouseEvent):

        if self.camera is None:
            return

        scroll_y = e.GetWheelRotation() / 120.0

        if e.CmdDown() and e.AltDown() and isinstance(self._transform_controller.TransformModel,
                                                      nornir_imageregistration.ITransformRelativeScaling):
            scale_delta = (1.0 + (-scroll_y / 50.0))
            self._transform_controller.TransformModel.ScaleWarped(scale_delta)
        elif e.CmdDown():  # We rotate when command is down
            angle = float(abs(scroll_y) * 2) ** 2.0
            if e.ShiftDown():
                angle = float(abs(scroll_y) / 2) ** 2.0

            rangle = (angle / 180.0) * 3.14159
            if scroll_y < 0:
                rangle = -rangle

            # print "Angle: " + str(angle)
            try:
                self._transform_controller.Rotate(rangle, np.array(
                    pyre.state.currentStosConfig.WarpedImageViewModel.Image.shape) / 2.0)
            except NotImplementedError:
                print("Current transform does not support rotation")
                pass

            # if isinstance(self._transform_controller.TransformModel, nornir_imageregistration.ITransformTargetRotation):
            #     self._transform_controller.TransformModel.RotateTargetPoints(-rangle,
            #                                       (state.currentStosConfig.FixedImageMaskViewModel.RawImageSize[0] / 2.0,
            #                                        state.currentStosConfig.FixedImageMaskViewModel.RawImageSize[1] / 2.0))
            # elif isinstance(self._transform_controller.TransformModel, nornir_imageregistration.ITransformSourceRotation):
            #     self._transform_controller.TransformModel.RotateSourcePoints(rangle,
            #                                           (state.currentStosConfig.WarpedImageViewModel.RawImageSize[
            #                                                0] / 2.0,
            #                                            state.currentStosConfig.WarpedImageViewModel.RawImageSize[
            #                                                1] / 2.0))

        else:
            zdelta = (1 + (-scroll_y / 20))

            new_scale = self.camera.scale * zdelta
            max_image_dimension_value = max(self._bounds.Width, self._bounds.Height)
            if self._transform_controller.width is not None:
                max_transform_dimension = max(self._transform_controller.width, self._transform_controller.height)
                max_image_dimension_value = max(max_image_dimension_value, max_transform_dimension)

            if new_scale > max_image_dimension_value * 2.0:
                new_scale = max_image_dimension_value * 2.0

            if new_scale < 0.5:
                new_scale = 0.5

            self.camera.scale = new_scale

            width, height = self.parent.GetSize()
            mouse_y, mouse_x = self.GetCorrectedMousePosition(e, height)
            world_coordinates = np.array(self.camera.ImageCoordsForMouse(x=mouse_x, y=mouse_y))

            # self.camera.lookat = scrolling_at_position[:2]
            print(f'Scrolling at {mouse_x}x {mouse_y}y mouse -> {world_coordinates[:2]} world')
            self._last_mouse_position = mouse_y, mouse_x

        self._statusbar.update_status_bar(self._last_mouse_position, in_target_space=False)

 


class DefaultImageTransformCommand(NavigationCommandBase):
    _executed: bool | None = None

    @property
    def executed(self) -> bool:
        return self._executed

    # A command that lets the user manipulate the camera and
    def subscribe_to_parent(self):
        self._bind_mouse_events()
        self._bind_key_events()

    def unsubscribe_to_parent(self):
        self._unbind_mouse_events()
        self._unbind_key_events()

    def can_execute(self) -> bool:
        return True

    def execute(self):
        _execute = True
        return

    def cancel(self):
        _execute = False
        return

    def on_key_down(self, event):
        return

    def on_key_up(self, event):
        return

    def on_mouse_press(self, event):
        return

    def on_mouse_release(self, event):
        return
