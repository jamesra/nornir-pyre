"""
Created on Feb 10, 2015

@author: u0490822
"""

from __future__ import annotations

from dependency_injector.wiring import Provide
import numpy as np
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QGuiApplication, QMouseEvent, QKeyEvent, QWheelEvent
import nornir_imageregistration

import abc
import math
import pyre
from pyre.selection_event_data import PointPair
import pyre.ui
from pyre.interfaces import StatusChangeCallback
from pyre.commands.uicommandbase import UICommandBase, InstantCommandBase
from pyre.interfaces.managers import ICommandHistory, ICommandQueue
from pyre.space import Space

from pyre.container import IContainer
from pyre.transform_edit_policy import (
    fixed_image_manipulation_locked,
    rigid_rotation_locked,
    wheel_rotate_locked,
)
from pyre.controllers.transform_display import gesture_for_wheel_rotate
from pyre.interfaces.viewtype import ViewType
from pyre.commands.extensions import wheel_scroll_steps
from pyre.views.composite_display import (
    lookat_delta_from_display_delta,
    world_point_pair_for_composite_mouse,
    display_lookat_for_composite,
    lookat_from_display_position,
    apply_composite_display_pan_delta,
    resolve_composite_display_draw_params,
    target_space_lookat_for_stos_view,
)
from pyre.views.gltiles import is_rigid_transform

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

    def _view_type(self) -> ViewType | None:
        """View type for the STOS panel hosting this command, if known."""
        panel = self._stos_image_panel()
        return panel.view_type if panel is not None else None

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

    def _adjust_camera_lookat_for_cursor(self, before: PointPair, after: PointPair) -> None:
        """Keep the world point under the cursor when zooming or panning."""
        view = self._view_type()
        model = self._transform_controller.TransformModel
        if view == ViewType.Composite and model is not None:
            if is_rigid_transform(model):
                delta_display = after.target - before.target
                delta_lookat = lookat_delta_from_display_delta(model, delta_display)
                self.camera.lookat = self.camera.lookat - delta_lookat
                return
            delta_display = after.target - before.target
            current_display = display_lookat_for_composite(self.camera, self._transform_controller)
            self.camera.lookat = lookat_from_display_position(
                self._transform_controller, current_display - delta_display)
            return
        delta = after[self.space] - before[self.space]
        self.camera.lookat = self.camera.lookat - delta

    def _translate_camera_by_display_delta(self, display_delta: tuple[float, float]) -> None:
        """Pan the camera; on composite, delta is in target display space."""
        view = self._view_type()
        model = self._transform_controller.TransformModel
        if view == ViewType.Composite and model is not None:
            apply_composite_display_pan_delta(
                self.camera, self._transform_controller, np.asarray(display_delta, dtype=np.float64))
            return
        self._camera.translate(display_delta)

    def get_world_positions(self, e: QMouseEvent | QWheelEvent | tuple[float, float]) -> PointPair:
        """
        Returns a tuple of the mouse position in both source and target space.
        When no transform is loaded (TransformModel is None) both spaces return the
        camera-space position so that panning and cursor tracking remain functional.
        :param e:
        :return:
        """
        y, x = NavigationCommandBase.ParamToMousePosition(e)
        cy, cx = self.GetCorrectedMousePosition((y, x), self.height)

        if self._view_type() == ViewType.Composite:
            composite_pair = world_point_pair_for_composite_mouse(
                self.camera, self._transform_controller, cy, cx)
            if composite_pair is not None:
                return composite_pair

        position = np.array(self.camera.ImageCoordsForMouse(cy, cx))

        if self._transform_controller.TransformModel is None:
            return PointPair(target=position, source=position)

        if self._space == Space.Source:
            mapped = np.squeeze(self._transform_controller.Transform(position))
            return PointPair(target=mapped,
                             source=position)
        elif self._space == Space.Target:
            mapped = np.squeeze(self._transform_controller.InverseTransform(position))
            return PointPair(target=position,
                             source=mapped)
        else:
            raise ValueError("Unknown space")

    def _keyboard_pan_delta(self, dy_frac: float, dx_frac: float) -> tuple[float, float]:
        """Return a display- or source-space pan step for WASD keyboard navigation."""
        view = self._view_type()
        model = self._transform_controller.TransformModel
        if view == ViewType.Composite and model is not None:
            _, bounds = resolve_composite_display_draw_params(
                self.camera,
                self._transform_controller,
                (self.height, self.parent.size().width()),
            )
            vis_h, vis_w = bounds.Height, bounds.Width
        else:
            vis_h = self.camera.visible_world_height
            vis_w = self.camera.visible_world_width
        return dy_frac * vis_h, dx_frac * vis_w

    def on_mouse_motion(self, event: QMouseEvent):
        """Called when the mouse moves"""

        try:
            width, height = self.parent.size().width(), self.parent.size().height()
            if width > 0 and height > 0:
                self.camera.window_size = np.array((height, width))
            (y, x) = self.GetCorrectedMousePosition(event, height)

            if self._last_mouse_position is None:
                self._last_mouse_position = (y, x)
                return

            # Only pan after a right-press established the drag; ignore buttoned moves that arrive first.
            if not (event.buttons() & Qt.MouseButton.RightButton):
                self._last_mouse_position = (y, x)
                return

            dx = x - self._last_mouse_position[nornir_imageregistration.iPoint.X]
            dy = (y - self._last_mouse_position[nornir_imageregistration.iPoint.Y])

            self._last_mouse_position = (y, x)

            self.camera.pan_by_screen_delta(dx, dy, width, height)

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

            scroll_y = wheel_scroll_steps(e)

            # Keep camera pixel geometry aligned with the GL panel for zoom/rotate-to-cursor.
            panel_w, panel_h = self.parent.size().width(), self.parent.size().height()
            if panel_w > 0 and panel_h > 0:
                self._width, self._height = panel_w, panel_h
                self.camera.window_size = np.array((panel_h, panel_w))

            # Wheel events can keep Shift/Ctrl from an earlier gesture; query live keys.
            wheel_mods = QGuiApplication.queryKeyboardModifiers()
            shift_scale = (
                (wheel_mods & Qt.KeyboardModifier.ShiftModifier)
                and not (wheel_mods & Qt.KeyboardModifier.ControlModifier)
                and isinstance(
                    self._transform_controller.TransformModel,
                    nornir_imageregistration.ITransformRelativeScaling)
            )
            if shift_scale and scroll_y != 0.0:
                scale_delta = (1.0 + (-scroll_y / 50.0))
                try:
                    point_pair = self.get_world_positions(e)
                    # ScaleWarpedAboutSourcePoint expects source-space pivot (same as rigid rotate).
                    source_pivot = np.asarray(point_pair.source, dtype=np.float32)
                    view = self._view_type()

                    self._transform_controller.begin_interactive_edit(
                        self.space,
                        view_type=self._view_type(),
                        gesture=gesture_for_wheel_rotate(
                            self.space, self._view_type(), self._transform_controller.type))
                    try:
                        self._transform_controller.ScaleWarped(
                            scale_delta, source_pivot, space=self.space)
                        if view == ViewType.Composite:
                            pair_after = self.get_world_positions(e)
                            self._adjust_camera_lookat_for_cursor(point_pair, pair_after)
                    finally:
                        self._transform_controller.end_interactive_edit()
                    self.parent.update()
                except NotImplementedError:
                    pass
            elif wheel_mods & Qt.KeyboardModifier.ControlModifier:  # rotate
                if wheel_rotate_locked(
                        self._transform_controller.type, self.space, self._view_type()):
                    pass
                else:
                    angle = float(abs(scroll_y) * 2) ** 2.0
                    if wheel_mods & Qt.KeyboardModifier.ShiftModifier:
                        angle = float(abs(scroll_y) / 2) ** 2.0

                    rangle = (angle / 180.0) * math.pi
                    if scroll_y < 0:
                        rangle = -rangle

                    # print "Angle: " + str(angle)
                    try:
                        point_pair = self.get_world_positions(e)
                        view = self._view_type()
                        if view == ViewType.Composite:
                            world_center = np.asarray(point_pair.source, dtype=np.float32)
                        elif self.space == Space.Source:
                            world_center = np.asarray(point_pair.source, dtype=np.float32)
                        else:
                            world_center = np.asarray(point_pair.target, dtype=np.float32)

                        self._transform_controller.begin_interactive_edit(
                            self.space,
                            view_type=self._view_type(),
                            gesture=gesture_for_wheel_rotate(
                                self.space, self._view_type(), self._transform_controller.type))
                        try:
                            self._transform_controller.Rotate(rangle, world_center, space=self.space)
                            if view == ViewType.Composite:
                                pair_after = self.get_world_positions(e)
                                self._adjust_camera_lookat_for_cursor(point_pair, pair_after)
                        finally:
                            self._transform_controller.end_interactive_edit()
                        self.parent.update()
                    except NotImplementedError:
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

                mouse_position = self.get_world_positions(e)

                new_scale = self.camera.scale * zdelta
                max_image_dimension_value = max(self._bounds.Width, self._bounds.Height)
                if self._transform_controller.width is not None:
                    max_transform_dimension = max(self._transform_controller.width, self._transform_controller.height)  # type: ignore[arg-type]
                    max_image_dimension_value = max(max_image_dimension_value, max_transform_dimension)

                if new_scale > max_image_dimension_value * 2.0:
                    new_scale = max_image_dimension_value * 2.0

                self.camera.scale = new_scale

                mouse_position_after_scale = self.get_world_positions(e)
                self._adjust_camera_lookat_for_cursor(mouse_position, mouse_position_after_scale)

                mouse_y, mouse_x = self.GetCorrectedMousePosition(e, self.height)
                self.parent.update()
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
            dy, dx = self._keyboard_pan_delta(0.0, -0.05)
            self._translate_camera_by_display_delta((dy, dx))
        elif symbol == 'd':  # "D" Character
            dy, dx = self._keyboard_pan_delta(0.0, 0.05)
            self._translate_camera_by_display_delta((dy, dx))
        elif symbol == 'w':  # "W" Character
            dy, dx = self._keyboard_pan_delta(0.05, 0.0)
            self._translate_camera_by_display_delta((dy, dx))
        elif symbol == 's':  # "S" Character
            dy, dx = self._keyboard_pan_delta(-0.05, 0.0)
            self._translate_camera_by_display_delta((dy, dx))

        elif keycode == Qt.Key.Key_PageUp:
            self.camera.scale *= 0.9
        elif keycode == Qt.Key.Key_PageDown:
            self.camera.scale *= 1.1
        # elif keycode == Qt.Key.Key_F1:
        #    self._image_transform_view.Debug = not self._image_transform_view.Debug
        elif symbol == 'm':
            # Match Source / Target / Composite to this window's center + scale.
            # Canonical sync space is Target (control); each panel converts for its camera.
            look_at = target_space_lookat_for_stos_view(
                self.camera,
                self._transform_controller,
                self.space,
                self._view_type(),
            )
            config = pyre.state.get_current_stos_config()
            if config is not None:
                config.WindowsLookAtFixedPoint(look_at, self.camera.scale)

        elif symbol == 'z' and e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.history_manager.Undo()
        elif symbol == 'x' and e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.history_manager.Redo()
        elif symbol == 'f':
            self._transform_controller.FlipWarped()
            self.history_manager.SaveState(self._transform_controller.FlipWarped)

        e.accept()

    def on_key_up(self, e: QKeyEvent) -> None:
        e.accept()
