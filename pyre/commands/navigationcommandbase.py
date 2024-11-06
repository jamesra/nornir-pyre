"""
Created on Feb 10, 2015

@author: u0490822
"""

from __future__ import annotations

from dependency_injector.wiring import Provide, inject
import numpy as np
import wx
import nornir_imageregistration

import abc
import pyre
from pyre.selection_event_data import PointPair
import pyre.ui
from pyre.command_interfaces import StatusChangeCallback
from pyre.commands.uicommandbase import UICommandBase, InstantCommandBase
from pyre.interfaces.managers import ICommandHistory, ICommandQueue
from pyre.space import Space

from pyre.container import IContainer


class NavigationCommandBase(UICommandBase, abc.ABC):
    """
    A command that needs to handle the mouse position in volume coordinates
    """

    _last_mouse_position: tuple[float, float]
    _transform_controller: pyre.state.TransformController

    # Bounds the camera is allowed to travel within
    _bounds: nornir_imageregistration.Rectangle

    _history_manager: ICommandHistory = Provide[pyre.container.IContainer.history_manager]

    _commandqueue: ICommandQueue

    config = Provide[IContainer.config]

    @property
    def history_manager(self) -> ICommandHistory:
        return self._history_manager

    @property
    def camera(self) -> pyre.ui.Camera:
        """The camera used by the command."""
        return self._camera

    @property
    def space(self) -> Space:
        """The space the command is operating in"""
        return self._space

    @inject
    def __init__(self,
                 parent: wx.Window,
                 transform_controller: pyre.viewmodels.TransformController,
                 camera: pyre.ui.Camera,
                 space: Space,
                 bounds: nornir_imageregistration.Rectangle,
                 commandqueue: ICommandQueue,
                 completed_func: StatusChangeCallback | None = None):
        """
        :param window parent: Window to subscribe to for events
        :param func completed_func: Function to call when command has completed
        :param Camera camera: Camera to use for mapping screen to volume coordinates
        :param commandqueue: Queue to add commands to if we need to start a new command
        """
        self._last_mouse_position = None
        self._space = space
        self._bounds = bounds
        self._transform_controller = transform_controller
        self._camera = camera
        self._commandqueue = commandqueue
        super(NavigationCommandBase, self).__init__(parent=parent,
                                                    completed_func=completed_func)

    @staticmethod
    def ParamToMousePosition(e: wx.MouseEvent | tuple[float, float]) -> tuple[float, float]:
        """
        :param e Either a wx.MouseEvent or a tuple of (y, x) coordinates:
        :return: (y, x) coordinates of mouse
        """

        if isinstance(e, tuple):
            y, x = e
        elif isinstance(e, wx.MouseEvent):
            x, y = e.GetPosition()
        else:
            raise ValueError("Unknown e type")

        return y, x

    @staticmethod
    def GetCorrectedMousePosition(e: wx.MouseEvent | tuple[float, float], height: int) -> tuple[float, float]:
        """wxPython inverts the mouse position, flip it back"""
        y, x = NavigationCommandBase.ParamToMousePosition(e)

        return height - y, x

    def get_space_position(self, e: wx.MouseEvent | tuple[float, float]) -> tuple[float, float]:
        """
        Return the mouse position in the source or target space, matching the source property of our instance
        :param e: wx.MouseEvent or (y,x) tuple
        :return: (y,x) tuple
        """
        y, x = NavigationCommandBase.ParamToMousePosition(e)
        cy, cx = self.GetCorrectedMousePosition((y, x), self.height)
        return self.camera.ImageCoordsForMouse(cy, cx)

    def get_world_positions(self, e: wx.MouseEvent | tuple[float, float]) -> PointPair:
        """
        Returns a tuple of the mouse position in both source and target space
        :param e:
        :return:
        """
        position = np.array(self.get_space_position(e))

        if self._space == Space.Source:
            return PointPair(target=np.squeeze(self._transform_controller.InverseTransform(position)),
                             source=position)
        elif self._space == Space.Target:
            return PointPair(target=position,
                             source=np.squeeze(self._transform_controller.InverseTransform(position)))
        else:
            raise ValueError("Unknown space")

    def on_mouse_motion(self, event: wx.MouseEvent):
        """Called when the mouse moves"""

        try:
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

            ImageDX = (float(dx) / width) * self.camera.visible_world_width
            ImageDY = (float(dy) / height) * self.camera.visible_world_height

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

        finally:
            event.Skip()

    def on_mouse_scroll(self, e: wx.MouseEvent):
        try:
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
                zdelta = (1 + (scroll_y / 20))

                new_scale = self.camera.scale * zdelta
                max_image_dimension_value = max(self._bounds.Width, self._bounds.Height)
                if self._transform_controller.width is not None:
                    max_transform_dimension = max(self._transform_controller.width, self._transform_controller.height)
                    max_image_dimension_value = max(max_image_dimension_value, max_transform_dimension)

                if new_scale > max_image_dimension_value * 2.0:
                    new_scale = max_image_dimension_value * 2.0

                self.camera.scale = new_scale

                width, height = self.parent.GetSize()
                mouse_y, mouse_x = self.GetCorrectedMousePosition(e, height)
                world_coordinates = np.array(self.camera.ImageCoordsForMouse(x=mouse_x, y=mouse_y))

                # self.camera.lookat = scrolling_at_position[:2]
                print(f'Scrolling at {mouse_x}x {mouse_y}y mouse -> {world_coordinates[:2]} world')
                self._last_mouse_position = mouse_y, mouse_x
        finally:
            e.Skip()

    def on_key_down(self, e):
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
            ImageDX = 0.1 * self.camera.visible_world_width
            self._camera.translate((-ImageDX, 0.0, float))
        elif symbol == 'd':  # "D" Character
            ImageDX = -0.1 * self.camera.visible_world_width
            self._camera.translate((ImageDX, 0.0, float))
        elif symbol == 'w':  # "W" Character
            ImageDY = -0.1 * self.camera.visible_world_height
            self._camera.translate((0, -ImageDY, float))
        elif symbol == 's':  # "S" Character
            ImageDY = 0.1 * self.camera.visible_world_height
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

            self.history_manager.SaveState(self._transform_controller.SetPoints, self._transform_controller.points)
        # elif symbol == 'l':
        #    self.show_lines = not self.show_lines
        # elif keycode == wx.WXK_F1:
        #    self._image_transform_view.Debug = not self._image_transform_view.Debug
        elif symbol == 'm':
            look_at = [self.camera.y, self.camera.x]

            # if not self.FixedSpace and self.ShowWarped:
            #    LookAt = self._transform_controller.transform([LookAt])
            #    LookAt = LookAt[0]

            pyre.state.currentStosConfig.WindowsLookAtFixedPoint(look_at, self.camera.scale)
            # pyre.SyncWindows(LookAt, self.camera.scale)

        elif symbol == 'z' and e.CmdDown():
            self.history_manager.Undo()
        elif symbol == 'x' and e.CmdDown():
            self.history_manager.Redo()
        elif symbol == 'f':
            self._transform_controller.FlipWarped()
            self.history_manager.SaveState(self._transform_controller.FlipWarped)
