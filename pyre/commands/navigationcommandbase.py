"""
Created on Feb 10, 2015

@author: u0490822
"""

from __future__ import annotations

from dependency_injector.wiring import Provide
import numpy as np
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QMouseEvent, QKeyEvent, QWheelEvent
import nornir_imageregistration

import abc
import pyre
from pyre.selection_event_data import PointPair
import pyre.ui
from pyre.interfaces import StatusChangeCallback
from pyre.commands.uicommandbase import UICommandBase, InstantCommandBase
from pyre.interfaces.managers import ICommandHistory, ICommandQueue
from pyre.space import Space

from pyre.container import IContainer

import pyre.ui.widgets.imagetransformviewpanel as imagetransformviewpanel_module


class NavigationCommandBase(UICommandBase, abc.ABC):
    """
    A command that needs to handle the mouse position in volume coordinates
    """

    _last_mouse_position: tuple[float, float] | None
    _transform_controller: pyre.state.TransformController  # type: ignore[attr-defined]

    # Bounds the camera is allowed to travel within
    _bounds: nornir_imageregistration.Rectangle

    _history_manager: ICommandHistory = Provide[pyre.container.IContainer.history_manager]  # type: ignore[attr-defined]

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

    def __init__(self,
                 parent: QWidget,
                 transform_controller: pyre.viewmodels.TransformController,  # type: ignore[attr-defined]
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

    def _stos_image_panel(self) -> imagetransformviewpanel_module.ImageTransformViewPanel | None:
        """Return the ImageTransformViewPanel hosting this command, if any (not mosaic)."""
        w = self.parent
        if w is None:
            return None
        cand = w.parent()
        if isinstance(cand, imagetransformviewpanel_module.ImageTransformViewPanel):
            return cand
        return None

    @staticmethod
    def ParamToMousePosition(e: QMouseEvent | QWheelEvent | tuple[float, float]) -> tuple[float, float]:
        """
        :param e Either a QMouseEvent or a tuple of (y, x) coordinates:
        :return: (y, x) coordinates of mouse
        """

        if isinstance(e, tuple):
            y, x = e
        elif isinstance(e, QMouseEvent) or isinstance(e, QWheelEvent):
            x, y = e.position().x(), e.position().y()
        else:
            raise ValueError("Unknown e type")

        return y, x

    @staticmethod
    def GetCorrectedMousePosition(e: QMouseEvent | QWheelEvent | tuple[float, float], height: int) -> tuple[float, float]:
        """Qt mouse coordinates have origin at top-left, convert to bottom-left origin"""
        y, x = NavigationCommandBase.ParamToMousePosition(e)

        return height - y, x

    def get_space_position(self, e: QMouseEvent | QWheelEvent | tuple[float, float]) -> tuple[float, float]:
        """
        Return the mouse position in the source or target space, matching the source property of our instance
        :param e: QMouseEvent or (y,x) tuple
        :return: (y,x) tuple
        """
        y, x = NavigationCommandBase.ParamToMousePosition(e)
        cy, cx = self.GetCorrectedMousePosition((y, x), self.height)
        return self.camera.ImageCoordsForMouse(cy, cx)  # type: ignore[return-value]

    def get_world_positions(self, e: QMouseEvent | QWheelEvent | tuple[float, float]) -> PointPair:
        """
        Returns a tuple of the mouse position in both source and target space.
        When no transform is loaded (TransformModel is None) both spaces return the
        camera-space position so that panning and cursor tracking remain functional.
        :param e:
        :return:
        """
        position = np.array(self.get_space_position(e))

        if self._transform_controller.TransformModel is None:
            return PointPair(target=position, source=position)

        if self._space == Space.Source:
            return PointPair(target=np.squeeze(self._transform_controller.InverseTransform(position)),
                             source=position)
        elif self._space == Space.Target:
            return PointPair(target=position,
                             source=np.squeeze(self._transform_controller.InverseTransform(position)))
        else:
            raise ValueError("Unknown space")

    def on_mouse_motion(self, event: QMouseEvent):
        """Called when the mouse moves"""

        try:
            width, height = self.parent.size().width(), self.parent.size().height()
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

            if event.buttons() & Qt.MouseButton.RightButton:
                self.camera.lookat = (self.camera.y - ImageDY, self.camera.x - ImageDX)

            # Commenting this block until I have a command to translate control points
            # if event.buttons() & Qt.MouseButton.LeftButton:
            #     if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            #         # Translate all points
            #         self._transform_controller.TranslateFixed((ImageDY, ImageDX))
            #     else:
            #         # Create a point or drag a point
            #         if self.SelectedPointIndex is not None:
            #             self.SelectedPointIndex = self._transform_controller.MovePoint(self.SelectedPointIndex, ImageDX,
            #                                                                            ImageDY, space=self.space)
            #         elif event.modifiers() & Qt.KeyboardModifier.ShiftModifier:  # The shift key is selected and we do not have a last point dragged
            #             return
            #         else:
            #             # find nearest point
            #             self.SelectedPointIndex = self._transform_controller.TryDrag(ImageX, ImageY, ImageDX, ImageDY,
            #                                                                          self.SelectionMaxDistance,
            #                                                                          space=self.space)

        finally:
            event.accept()

    def on_mouse_scroll(self, e: QWheelEvent):
        try:
            if self.camera is None:
                return

            # Qt wheel events use angleDelta which is in eighths of a degree
            # Divide by 120 to get a similar scale to wx's GetWheelRotation
            scroll_y = e.angleDelta().y() / 120.0

            if (e.modifiers() & Qt.KeyboardModifier.ControlModifier) and (
                    e.modifiers() & Qt.KeyboardModifier.AltModifier) and isinstance(
                    self._transform_controller.TransformModel,
                    nornir_imageregistration.ITransformRelativeScaling):
                scale_delta = (1.0 + (-scroll_y / 50.0))
                self._transform_controller.TransformModel.ScaleWarped(scale_delta)
            elif e.modifiers() & Qt.KeyboardModifier.ControlModifier:  # We rotate when command is down
                angle = float(abs(scroll_y) * 2) ** 2.0
                if e.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    angle = float(abs(scroll_y) / 2) ** 2.0

                rangle = (angle / 180.0) * 3.14159
                if scroll_y < 0:
                    rangle = -rangle

                # print "Angle: " + str(angle)
                try:
                    width, height = self.parent.size().width(), self.parent.size().height()

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
                zdelta = (1 + (scroll_y / 40))

                # Use current parent size so zoom-to-cursor is correct on all panels (fixed/composite/warped).
                # Command dimensions can be stale if resize fired before glpanel was laid out.
                self._width, self._height = self.parent.size().width(), self.parent.size().height()

                mouse_position = self.get_world_positions(e)
                screen_center = self.get_world_positions((self.height / 2, self.width / 2))

                new_scale = self.camera.scale * zdelta
                max_image_dimension_value = max(self._bounds.Width, self._bounds.Height)
                if self._transform_controller.width is not None:
                    max_transform_dimension = max(self._transform_controller.width, self._transform_controller.height)  # type: ignore[arg-type]
                    max_image_dimension_value = max(max_image_dimension_value, max_transform_dimension)

                if new_scale > max_image_dimension_value * 2.0:
                    new_scale = max_image_dimension_value * 2.0

                self.camera.scale = new_scale

                mouse_position_after_scale = self.get_world_positions(e)
                delta = mouse_position_after_scale[self.space] - mouse_position[self.space]

                self.camera.lookat = self.camera.lookat - delta

                mouse_y, mouse_x = self.GetCorrectedMousePosition(e, self.height)

                # print(
                #    f'Scrolling at {mouse_x}x {mouse_y}y mouse -> {self.space} {mouse_position.source} source {mouse_position.target} target')
                self._last_mouse_position = mouse_y, mouse_x
        finally:
            e.accept()

    def on_key_down(self, e: QKeyEvent):
        keycode = e.key()

        symbol = ''
        try:
            # Convert key code to character if it's a printable ASCII character
            if 32 <= keycode <= 126:  # ASCII printable characters
                key_char = chr(keycode)
                symbol = key_char.lower()
        except:
            pass

        panel = self._stos_image_panel()
        if keycode == Qt.Key.Key_Tab and not (e.modifiers() & Qt.KeyboardModifier.ControlModifier):
            if panel is not None:
                self._transform_controller.NextViewMode()
                self.parent.update()
            e.accept()
            return

        if symbol == 'l' and panel is not None:
            panel.show_lines = not panel.show_lines
            self.parent.update()
            e.accept()
            return

        if symbol == 'a':  # "A" Character
            ImageDX = -0.05 * self.camera.visible_world_width
            self._camera.translate((0.0, ImageDX))
        elif symbol == 'd':  # "D" Character
            ImageDX = 0.05 * self.camera.visible_world_width
            self._camera.translate((0, ImageDX))
        elif symbol == 'w':  # "W" Character
            ImageDY = 0.05 * self.camera.visible_world_height
            self._camera.translate((ImageDY, 0))
        elif symbol == 's':  # "S" Character
            ImageDY = -0.05 * self.camera.visible_world_height
            self._camera.translate((ImageDY, 0))

        elif keycode == Qt.Key.Key_PageUp:
            self.camera.scale *= 0.9
        elif keycode == Qt.Key.Key_PageDown:
            self.camera.scale *= 1.1
        # elif keycode == Qt.Key.Key_F1:
        #    self._image_transform_view.Debug = not self._image_transform_view.Debug
        elif symbol == 'm':
            look_at = [self.camera.y, self.camera.x]

            # if not self.FixedSpace and self.ShowWarped:
            #    LookAt = self._transform_controller.transform([LookAt])
            #    LookAt = LookAt[0]

            config = pyre.state.get_current_stos_config()
            if config is not None:
                config.WindowsLookAtFixedPoint(look_at, self.camera.scale)
            # pyre.common.sync_stos_windows(look_at, self.camera.scale)

        elif symbol == 'z' and e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.history_manager.Undo()
        elif symbol == 'x' and e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.history_manager.Redo()
        elif symbol == 'f':
            self._transform_controller.FlipWarped()
            self.history_manager.SaveState(self._transform_controller.FlipWarped)

        e.accept()
