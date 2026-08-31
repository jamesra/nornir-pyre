from __future__ import annotations

import typing

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
from pyre.interfaces.viewtype import ViewType
from pyre.selection_event_data import PointPair
from pyre import common as pyre_common
from pyre.views.composite_display import (
    display_lookat_for_composite,
    lookat_from_display_position,
)
from pyre.views.gltiles import is_rigid_transform


class ManipulateRigidTransformCommand(NavigationCommandBase):
    """This command takes a selection of control points and adjusts the position"""

    _space: Space
    _translate_origin: NDArray[np.floating] | None
    # Parameter snapshot, not the model. All STOS windows share one model and
    # Translate mutates it in place, so holding a reference here made cancel a
    # no-op that committed the gesture.
    _original_state: dict[str, typing.Any]

    @property
    def transform(self) -> IRigidTransform:
        return self._transform_controller.transform  # type: ignore[attr-defined]

    _mouse_position_history: IMousePositionHistoryManager = Provide[IContainer.mouse_position_history]
    _window_manager: IWindowManager = Provide[IContainer.window_manager]

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
        # Defer origin until the first motion so a stale shared mouse history cannot jump the layer.
        self._translate_origin = None
        self._selected_point_set = selected_points

        if not isinstance(self._transform_controller.TransformModel, IRigidTransform):
            raise ValueError("Transform controller must have a rigid transform model")

        self._original_state = transform_controller.TransformModel.GetRigidState()

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

    def _world_point_for_translate(self, point_pair: PointPair) -> NDArray[np.floating]:
        """Return world coords whose delta tracks on-screen motion for this panel."""
        if self._view_type() == ViewType.Composite:
            return point_pair.target
        return point_pair.source if self.space == Space.Source else point_pair.target

    def on_mouse_motion(self, event: QMouseEvent):
        """Called when the mouse is dragged"""

        if event.buttons() & Qt.MouseButton.RightButton:
            # super().on_mouse_motion(event)
            self.cancel()
            return

        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return

        point_pair = self.get_world_positions(event)
        world_point = self._world_point_for_translate(point_pair)

        if self._translate_origin is None:
            self._translate_origin = world_point
            return

        delta = world_point - self._translate_origin
        if self.space == Space.Source:
            delta = -delta

        self._transform_controller.Translate(delta, space=self.space)

        # Re-derive the origin *after* the mutation rather than reusing world_point. On
        # composite the drag quantity is target-display space, which Translate just moved
        # under a stationary cursor, so the next delta must be measured from the new frame;
        # reusing world_point double-counts each step (measured 2.3x overshoot). On the
        # standalone panels the drag quantity is the raw camera position, so this is a no-op
        # and both forms track 1:1. Keep it: dropping it only breaks composite. (#158)
        point_pair = self.get_world_positions(event)
        self._translate_origin = self._world_point_for_translate(point_pair)

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
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                multiplier *= 5
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                multiplier *= 25

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

            if self._space == Space.Source:
                delta[0] = -delta[0]
                delta[1] = -delta[1]

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
        self._transform_controller.begin_interactive_edit(
            self.space, view_type=self._view_type())

    def on_mouse_scroll(self, event: QWheelEvent):
        """Delegate zoom/rotate to navigation while a translate drag is active."""
        NavigationCommandBase.on_mouse_scroll(self, event)

    def on_key_up(self, event: QKeyEvent):
        """Called when a key is released"""
        pass

    def can_execute(self) -> bool:
        return True

    def _end_interactive_edit_preserving_composite_display(self) -> None:
        """End the gesture without letting composite view_proj jump onto the source.

        Capture target-display lookat while the translate freeze is still active,
        clear the gesture, then rebase ``camera.lookat`` so live ``Transform(lookat)``
        matches that same display point.
        """
        display_yx: NDArray[np.floating] | None = None
        if self._view_type() == ViewType.Composite:
            model = self._transform_controller.TransformModel
            if model is not None and is_rigid_transform(model):
                display_yx = display_lookat_for_composite(
                    self.camera, self._transform_controller)
        self._transform_controller.end_interactive_edit()
        if display_yx is not None:
            self.camera.lookat = lookat_from_display_position(
                self._transform_controller, display_yx)

    def _restore_original_state(self) -> None:
        """Undo the gesture by restoring the parameters captured at construction.

        Restores onto the shared model instance rather than reassigning
        ``TransformModel``; every STOS view holds that same object, so replacing
        it would strand them on the abandoned transform.
        """
        model = self._transform_controller.TransformModel
        if not isinstance(model, IRigidTransform):
            return

        model.SetRigidState(self._original_state)

    def cancel(self):
        display_yx: NDArray[np.floating] | None = None
        if self._view_type() == ViewType.Composite:
            model = self._transform_controller.TransformModel
            if model is not None and is_rigid_transform(model):
                display_yx = display_lookat_for_composite(
                    self.camera, self._transform_controller)
        self._transform_controller.end_interactive_edit()
        self._restore_original_state()
        if display_yx is not None:
            self.camera.lookat = lookat_from_display_position(
                self._transform_controller, display_yx)
        super().cancel()
        return

    def execute(self):
        self._end_interactive_edit_preserving_composite_display()
        super().execute()

    def subscribe_to_parent(self):
        self._bind_mouse_events()
        self._bind_key_events()

    def unsubscribe_to_parent(self):
        self._unbind_mouse_events()
        self._unbind_key_events()

