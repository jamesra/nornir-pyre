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
from pyre.space import Space

import pyre.ui

from pyre.ui.camerastatusbar import CameraStatusBar


class NavigationCommandBase(CommandBase):
    """
    A command that needs to handle the mouse position in volume coordinates
    """

    _last_mouse_position: tuple[float, float]
    _statusbar: CameraStatusBar | None
    _transform_controller: pyre.state.TransformController

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
        self._last_mouse_position = None
        super(NavigationCommandBase, self).__init__(parent=parent,
                                                    completed_func=completed_func)

    def GetCorrectedMousePosition(self, e: wx.MouseEvent, height: int) -> tuple[float, float]:
        """wxPython inverts the mouse position, flip it back"""
        (x, y) = e.GetPosition()
        return height - y, x

    def on_mouse_motion(self, event: wx.MouseEvent):
        """Called when the mouse moves"""
        width, height = self.parent.GetClientSize()
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
            self._statusbar.update_status_bar(self._last_mouse_position, in_target_space=False)

        if event.RightIsDown():
            self.camera.lookat = (self.camera.y - ImageDY, self.camera.x - ImageDX)

        # Commenting this block until I have a command to translate control points
        # if event.LeftIsDown():
        #     if event.CmdDown():
        #         # Translate all points
        #         self._transform_controller.TranslateFixed((ImageDY, ImageDX))
        #     else:
        #         # Create a point or drag a point
        #         if self.SelectedPointIndex is not None:
        #             self.SelectedPointIndex = self._transform_controller.MovePoint(self.SelectedPointIndex, ImageDX,
        #                                                                            ImageDY, space=self.space)
        #         elif event.ShiftDown():  # The shift key is selected and we do not have a last point dragged
        #             return
        #         else:
        #             # find nearest point
        #             self.SelectedPointIndex = self._transform_controller.TryDrag(ImageX, ImageY, ImageDX, ImageDY,
        #                                                                          self.SelectionMaxDistance,
        #                                                                          space=self.space)
        self._statusbar.update_status_bar(self._last_mouse_position, in_target_space=False)

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
                width, height = self.parent.GetClientSize()

                area = np.array([height, width])
                center = area / 2.0
                world_center = self.camera.ImageCoordsForMouse(center[0], center[1])

                self._transform_controller.Rotate(rangle, world_center)
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

    def on_key_press(self, e):
        keycode = e.GetKeyCode()

        symbol = ''
        try:
            key_char = '%c' % keycode
            symbol = key_char.lower()
        except:
            pass

        # if keycode == wx.WXK_TAB:
        #     try:
        #         if self.composite:
        #             self.NextGLFunction()
        #         else:
        #             self.ShowWarped = not self.ShowWarped
        #     except:
        #         pass

        if symbol == 'a':  # "A" Character
            ImageDX = 0.1 * self.camera.ViewWidth
            self._camera.translate((-ImageDX, 0.0, float))
        elif symbol == 'd':  # "D" Character
            ImageDX = -0.1 * self.camera.ViewWidth
            self._camera.translate((ImageDX, 0.0, float))
        elif symbol == 'w':  # "W" Character
            ImageDY = -0.1 * self.camera.ViewHeight
            self._camera.translate((0, -ImageDY, float))
        elif symbol == 's':  # "S" Character
            ImageDY = 0.1 * self.camera.ViewHeight
            self._camera.translate((0, ImageDY, float))

        elif keycode == wx.WXK_PAGEUP:
            self.camera.scale *= 0.9
        elif keycode == wx.WXK_PAGEDOWN:
            self.camera.scale *= 1.1
        elif keycode == wx.WXK_SPACE:

            # If SHIFT is held down, align everything.  Otherwise align the selected point
            if not e.ShiftDown() and not self.HighlightedPointIndex is None:
                self.SelectedPointIndex = self._transform_controller.AutoAlignPoints(self.HighlightedPointIndex)

            elif e.ShiftDown():
                self._transform_controller.AutoAlignPoints(range(0, self._transform_controller.NumPoints))

            pyre.history.SaveState(self._transform_controller.SetPoints, self._transform_controller.points)
        # elif symbol == 'l':
        #    self.show_lines = not self.show_lines
        # elif keycode == wx.WXK_F1:
        #    self._image_transform_view.Debug = not self._image_transform_view.Debug
        elif symbol == 'm':
            LookAt = [self.camera.y, self.camera.x]

            # if not self.FixedSpace and self.ShowWarped:
            #    LookAt = self._transform_controller.transform([LookAt])
            #    LookAt = LookAt[0]

            pyre.state.currentStosConfig.WindowsLookAtFixedPoint(LookAt, self.camera.scale)
            # pyre.SyncWindows(LookAt, self.camera.scale)

        elif symbol == 'z' and e.CmdDown():
            pyre.history.Undo()
        elif symbol == 'x' and e.CmdDown():
            pyre.history.Redo()
        elif symbol == 'f':
            self._transform_controller.FlipWarped()
            pyre.history.SaveState(self._transform_controller.FlipWarped)


class DefaultImageTransformCommand(NavigationCommandBase):
    _executed: bool | None = None

    @property
    def executed(self) -> bool:
        return self._executed

    @property
    def SelectionMaxDistance(self) -> float:
        """How close we need to be to a control point to select it"""
        selection_max_distance = (float(self.camera.ViewHeight) / float(self.height)) * 20.0
        if selection_max_distance < 16:
            selection_max_distance = 16

        return selection_max_distance

    # A command that lets the user manipulate the camera and
    def subscribe_to_parent(self):
        self._bind_mouse_events()
        self._bind_key_events()
        self._bind_resize_event()

    def unsubscribe_to_parent(self):
        self._unbind_mouse_events()
        self._unbind_key_events()
        self._unbind_resize_event()

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


class TranslatePointSelectionCommand(NavigationCommandBase):
    """This command takes a selection of control points and adjusts the position"""

    _selected_points: list[int]  # The indices of the selected points
    _space: Space

    def __init__(self,
                 parent: wx.Window,
                 status_bar: CameraStatusBar,
                 transform_controller: pyre.viewmodels.TransformController,
                 camera: pyre.ui.Camera,
                 bounds: nornir_imageregistration.Rectangle,
                 selected_points: list[int],  # The indices of the selected points
                 space: Space,  # Space we are moving the points in, source or target side
                 completed_func: CompletionCallback = None):
        super().__init__(parent, status_bar, transform_controller, camera, bounds, completed_func)
        self._selected_points = selected_points

    def on_mouse_press(self, event: wx.MouseEvent):
        """Called when the mouse is pressed"""
        pass

    def on_mouse_release(self, event: wx.MouseEvent):
        """Called when the mouse is released"""
        self.execute()

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

            pyre.history.SaveState(self._transform_controller.SetPoints, self._transform_controller.points)

        return

    def on_mouse_scroll(self, event: wx.MouseEvent):
        """Called when the mouse wheel is scrolled"""
        pass

    def on_mouse_drag(self, event: wx.MouseEvent):
        """Called when the mouse is dragged"""
        pass
