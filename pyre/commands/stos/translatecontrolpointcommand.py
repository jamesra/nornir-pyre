from __future__ import annotations

from dependency_injector.wiring import inject, Provide
import numpy as np
from numpy._typing import NDArray
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QMouseEvent, QKeyEvent

import nornir_imageregistration
import pyre
from pyre.observable import ObservableSet, ObservedAction
from pyre import Space
from pyre.interfaces import StatusChangeCallback
from pyre.commands import NavigationCommandBase
from pyre.commands.commandexceptions import RequiresSelectionError
from pyre.interfaces.managers import ICommandQueue, IMousePositionHistoryManager, IWindowManager
from pyre.interfaces.viewtype import ViewType
from pyre.container import IContainer
from pyre.selection_event_data import PointPair
from pyre import common as pyre_common
from pyre.views.gltiles import is_rigid_transform


class TranslateControlPointCommand(NavigationCommandBase):
    """This command takes a selection of control points and adjusts the position"""

    _selected_point_set: ObservableSet[int]  # The indices of the selected points
    _command_points: set[int]  # Points under mouse when command was triggered
    _space: Space
    _translate_origin: NDArray[np.floating] | None
    _original_points: NDArray[np.floating]

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
                 completed_func: StatusChangeCallback | None = None,
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
        # Defer origin until the first motion so a stale shared mouse history cannot jump points.
        self._translate_origin = None
        self._selected_point_set = selected_points

        if translate_all:
            self._command_points = set(range(transform_controller.NumPoints))
        else:
            combined_command_points = set(selected_points)
            combined_command_points.update(command_points)
            self._command_points = combined_command_points

        if len(self._command_points) == 0:
            raise RequiresSelectionError()

        self._original_points = transform_controller.copy_points()

    def __str__(self):
        return "TranslateControlPointCommand"

    def _world_point_for_translate(self, point_pair: PointPair) -> NDArray[np.floating]:
        """Return world coords for CP drag delta in this panel's command space."""
        model = self._transform_controller.TransformModel
        if (
                self._view_type() == ViewType.Composite
                and model is not None
                and not is_rigid_transform(model)
        ):
            return point_pair.target
        return point_pair.source if self.space == Space.Source else point_pair.target

    def _edit_space_for_translate(self) -> Space:
        """Space passed to MovePoint for this drag.

        Composite mesh/grid glyphs are in target display space. Grid transforms only
        edit TargetPoints, so composite drags must update Target even though the
        panel command space is Source.
        """
        model = self._transform_controller.TransformModel
        if (
                self._view_type() == ViewType.Composite
                and model is not None
                and not is_rigid_transform(model)
        ):
            return Space.Target
        return self.space

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
            self.cancel()
            return

        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return

        # Use current parent size so deltas are correct (e.g. in composite after resize)
        self._width, self._height = self.parent.size().width(), self.parent.size().height()
        point_pair = self.get_world_positions(event)

        world_point = self._world_point_for_translate(point_pair)

        if self._translate_origin is None:
            self._translate_origin = world_point
            return

        delta = world_point - self._translate_origin
        self._translate_origin = world_point

        new_selected_indicies = self._transform_controller.MovePoint(
            list(self._selected_point_set),
            delta[1],
            delta[0],
            space=self._edit_space_for_translate(),
        )

        # Update selected points in the UI if indicies have changed
        new_indices_set = set(np.atleast_1d(new_selected_indicies).tolist())
        if len(new_indices_set - self._selected_point_set) > 0:
            self._selected_point_set.clear()
            self._selected_point_set.update(new_indices_set)

        # Request repaint so control point movement is visible during drag (change listeners are deferred)
        self.parent.update()

        # Peers already receive OnPointMoved and refresh their buffers, but their update()
        # stays queued while this panel holds the mouse grab, so they render stale until
        # mouse-up. Repaint them synchronously, as the rigid drag does. Unconditional
        # because moving a control point can rewrite either space -- MovePoint maps a
        # source-space drag onto TargetPoints for target-only models -- so there is no
        # space for which the peers are guaranteed unaffected. Last in the handler, after
        # the origin and selection are consistent, since the helper pumps the event queue
        # and a queued motion can re-enter here. (#166)
        pyre_common.repaint_peer_stos_gl_panels(self._window_manager, exclude_gl_panel=self.parent)

    def on_key_down(self, event: QKeyEvent):
        """Called when a key is pressed"""
        keycode = event.key()

        if (keycode == Qt.Key.Key_Left or
            keycode == Qt.Key.Key_Right or
            keycode == Qt.Key.Key_Up or
            keycode == Qt.Key.Key_Down) and self.HighlightedPointIndex is not None:  # type: ignore[attr-defined]

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

            self._transform_controller.MovePoint(
                list(self._selected_point_set),
                delta[1],
                delta[0],
                space=self._edit_space_for_translate(),
            )
        return

    def activate(self):
        super().activate()
        # Use the MovePoint space (Target on composite mesh/grid), not the panel command space.
        self._transform_controller.begin_interactive_edit(
            self._edit_space_for_translate(),
            view_type=self._view_type(),
        )
        self._selected_point_set.update(
            self._command_points)  # Ensure the command points are included in the selected points

    def on_mouse_scroll(self, event: QMouseEvent):
        """Called when the mouse wheel is scrolled"""
        pass

    def on_key_up(self, event: QKeyEvent):
        """Called when a key is released"""
        pass

    def can_execute(self) -> bool:
        return True

    def cancel(self):
        self._transform_controller.end_interactive_edit()
        self._transform_controller.SetPoints(self._original_points)
        super().cancel()
        return

    def execute(self):
        self._transform_controller.end_interactive_edit()
        super().execute()

    def subscribe_to_parent(self):
        self._bind_mouse_events()
        # Do not chain prior mouse/wheel handlers while translating points.
        # Chained handlers can process the same drag and effectively double-apply deltas.
        # Chained wheel would still run NavigationCommandBase (camera zoom or Shift+ScaleWarped).
        self._saved_mousePressEvent = None
        self._saved_mouseMoveEvent = None
        self._saved_mouseReleaseEvent = None
        self._saved_wheelEvent = None
        self._bind_key_events()

    def unsubscribe_to_parent(self):
        self._unbind_mouse_events()
        self._unbind_key_events()

