from __future__ import annotations

from dependency_injector.wiring import inject, Provide
import numpy as np
from numpy._typing import NDArray
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QMouseEvent, QKeyEvent, QWheelEvent

import nornir_imageregistration
from nornir_imageregistration import IRigidTransform
import pyre
from pyre.observable import ObservableSet, ObservedAction
from pyre import Space
from pyre.interfaces import StatusChangeCallback
from pyre.commands import NavigationCommandBase
from pyre.commands.commandexceptions import RequiresSelectionError
from pyre.interfaces.managers import ICommandQueue, IMousePositionHistoryManager, IWindowManager
from pyre.container import IContainer
from pyre.transform_edit_policy import fixed_image_manipulation_locked
from pyre import common as pyre_common


class ManipulateRigidTransformCommand(NavigationCommandBase):
    """This command takes a selection of control points and adjusts the position"""

    _space: Space
    _translate_origin: NDArray[np.floating]
    _original_points: NDArray[np.floating]

    @property
    def transform(self) -> IRigidTransform:
        return self._transform_controller.transform  # type: ignore[attr-defined]

    _mouse_position_history: IMousePositionHistoryManager = Provide[IContainer.mouse_position_history]
    _window_manager: IWindowManager = Provide[IContainer.window_manager]

    @property
    def translated_points(self) -> NDArray[np.floating]:
        return self._transform_controller.points[list(self._selected_point_set)]  # type: ignore[index]

    @inject
    def __init__(self,
                 parent: QWidget,
                 camera: pyre.ui.Camera,
                 bounds: nornir_imageregistration.Rectangle,
                 selected_points: ObservableSet[int],  # The indices of the selected points
                 command_points: set[int],  # Points under mouse when command was triggered
                 space: Space,  # Space we are moving the points in, source or target side
                 commandqueue: ICommandQueue,
                 translate_all: bool = False,  # True if all points in the transform should be translated
                 completed_func: StatusChangeCallback | None = None,  # type: ignore[assignment]
                 transform_controller: pyre.viewmodels.TransformController = Provide[IContainer.transform_controller],  # type: ignore[attr-defined]
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

        if not isinstance(self._transform_controller.TransformModel, IRigidTransform):
            raise ValueError("Transform controller must have a rigid transform model")

        self._original_points = transform_controller.TransformModel

    def __str__(self):
        return "ManipulateRigidTransformCommand"

    def on_mouse_press(self, event: QMouseEvent):
        """Called when the mouse is pressed"""
        if event.buttons() & Qt.MouseButton.MiddleButton or event.buttons() & Qt.MouseButton.RightButton:
            self.cancel()  # Cancel if the middle mouse button is pressed

    def on_mouse_release(self, event: QMouseEvent):
        """Called when the mouse is released"""
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            self.execute()

    def on_mouse_motion(self, event: QMouseEvent):
        """Called when the mouse is dragged"""

        if event.buttons() & Qt.MouseButton.RightButton:
            # super().on_mouse_motion(event)
            self.cancel()
            return

        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return

        point_pair = self.get_world_positions(event)
        world_point = point_pair.source if self.space == Space.Source else point_pair.target

        delta = world_point - self._translate_origin
        camera_delta = delta
        if self.space == Space.Source:
            delta = delta
            camera_delta = -delta
        else:
            camera_delta = delta
            delta = -delta

        # if self.view
        # self.camera.translate(camera_delta)  # Balance out translation with camera movement so the correct layer appears to move

        # print(
        #    f'space: {self.space} x:{world_point[1]} y:{world_point[0]} hx:{self._translate_origin[1]} hy:{self._translate_origin[0]} dx:{delta[1]} dy:{delta[0]}')

        self._transform_controller.Translate(delta, space=self.space)

        # Update the last position with the new mouse position
        point_pair = self.get_world_positions(event)
        world_point = point_pair.source if self.space == Space.Source else point_pair.target
        self._translate_origin = world_point

        self.parent.update()
        if self.space == Space.Target:
            pyre_common.repaint_peer_stos_gl_panels(self._window_manager, exclude_gl_panel=self.parent)

    def on_key_down(self, event: QKeyEvent):
        """Called when a key is pressed"""
        if fixed_image_manipulation_locked(
                self._transform_controller.type, self.space, self._view_type()):
            return

        keycode = event.key()

        if (keycode == Qt.Key.Key_Left or
                keycode == Qt.Key.Key_Right or
                keycode == Qt.Key.Key_Up or
                keycode == Qt.Key.Key_Down):

            # Users can nudge points with the arrow keys.  Holding shift steps five pixels, holding Ctrl shifts 25.  Holding both steps 125
            multiplier = 1
            print(str(multiplier))
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                multiplier *= 5
                print(str(multiplier))
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                multiplier *= 25
                print(str(multiplier))

            delta = [0, 0]
            if keycode == Qt.Key.Key_Left:
                delta = [0, -1]
            elif keycode == Qt.Key.Key_Right:
                delta = [0, 1]
            elif keycode == Qt.Key.Key_Up:
                delta = [1, 0]
            elif keycode == Qt.Key.Key_Down:
                delta = [-1, 0]

            delta[0] *= multiplier
            delta[1] *= multiplier

            self._transform_controller.Translate(delta,
                                                 space=self._space)

        return

    def on_mouse_wheel(self, event: QMouseEvent):
        """Legacy handler retained for compatibility; Qt dispatch uses on_mouse_scroll."""
        self.on_mouse_scroll(event)

    def activate(self):
        super().activate()
        if fixed_image_manipulation_locked(
                self._transform_controller.type, self.space, self._view_type()):
            self.cancel()
            return
        self._transform_controller.begin_interactive_edit(self.space)

    def on_mouse_scroll(self, event: QWheelEvent):
        """Delegate zoom/rotate to navigation while a translate drag is active."""
        NavigationCommandBase.on_mouse_scroll(self, event)

    def on_key_up(self, event: QKeyEvent):
        """Called when a key is released"""
        pass

    def can_execute(self) -> bool:
        return True

    def cancel(self):
        self._transform_controller.end_interactive_edit()
        self._transform_controller.TransformModel = self._original_points  # type: ignore[assignment]
        super().cancel()
        return

    def execute(self):
        self._transform_controller.end_interactive_edit()
        super().execute()

    def subscribe_to_parent(self):
        self._bind_mouse_events()
        self._bind_key_events()

    def unsubscribe_to_parent(self):
        self._unbind_mouse_events()
        self._unbind_key_events()

