from __future__ import annotations

import logging

import numpy as np
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget, QMessageBox
from PyQt6.QtGui import QMouseEvent, QKeyEvent, QCursor
from dependency_injector.wiring import Provide, inject
from dependency_injector.providers import Dict, Factory
from logging import Logger

import nornir_imageregistration
from nornir_imageregistration.transforms import IControlPointEdit, IControlPoints
from nornir_imageregistration.transforms.transform_type import TransformType
from nornir_imageregistration.transforms import ConvertTransform
from pyre.commands.commandexceptions import RequiresSelectionError
from pyre.interfaces import ControlPointAction, SetSelectionCallable
from pyre.observable import ObservableSet, SetOperation
from pyre.selection_event_data import InputEvent, SelectionEventData, InputSource, PointPair, SelectionEventKey
from pyre.interfaces import ICommand, IInstantCommand, StatusChangeCallback
from pyre.interfaces.managers import ICommandQueue, IMousePositionHistoryManager, IControlPointMapManager, \
    IControlPointActionMap, ControlPointManagerKey, IImageManager
from pyre.interfaces.viewtype import ViewType
from pyre.controllers import TransformController
import pyre.views.pointview
from pyre.space import Space
from pyre.commands.navigationcommandbase import NavigationCommandBase
from pyre.container import IContainer
from pyre.commands.extensions import GetKeyModifiers, GetMouseModifiers
import pyre.ui
from pyre.transform_edit_policy import blocks_layer_translate_action, blocks_control_point_translate_action, fixed_image_manipulation_locked
from pyre.views.composite_display import (
    apply_composite_display_pan_delta,
    world_point_pair_for_composite_mouse,
)
from pyre.views.gltiles import is_rigid_transform

REGION_DRAG_THRESHOLD_PX = 5.0

DEFAULT_CURSOR_SHAPES: dict[ControlPointAction, Qt.CursorShape] = {
    ControlPointAction.NONE: Qt.CursorShape.ArrowCursor,
    ControlPointAction.CREATE: Qt.CursorShape.CrossCursor,
    ControlPointAction.CREATE_REGISTER: Qt.CursorShape.CrossCursor,
    ControlPointAction.DELETE: Qt.CursorShape.ForbiddenCursor,
    ControlPointAction.TRANSLATE: Qt.CursorShape.OpenHandCursor,
    ControlPointAction.REGISTER: Qt.CursorShape.WhatsThisCursor,
    ControlPointAction.TRANSLATE | ControlPointAction.REGISTER: Qt.CursorShape.OpenHandCursor,
    ControlPointAction.DELETE | ControlPointAction.TRANSLATE | ControlPointAction.REGISTER: Qt.CursorShape.OpenHandCursor,
    ControlPointAction.TRANSLATE_ALL: Qt.CursorShape.CrossCursor,
    ControlPointAction.CALL_TO_MOUSE: Qt.CursorShape.CrossCursor,
    ControlPointAction.BOX_SELECT: Qt.CursorShape.CrossCursor,
    ControlPointAction.LASSO_SELECT: Qt.CursorShape.CrossCursor,
}


def _build_default_cursor_action_map() -> dict[ControlPointAction, QCursor]:
    # QCursor creation requires a live QGuiApplication, so keep it lazy.
    return {action: QCursor(shape) for action, shape in DEFAULT_CURSOR_SHAPES.items()}


class DefaultTransformCommand(NavigationCommandBase):
    """
    Supports:
     1. Navigating around the view of the images.
     2. Selecting control points
    """
    _executed: bool = False

    config = Provide[IContainer.config]

    _controlpointmap: pyre.viewmodels.ControlPointMap
    _actionmap: IControlPointActionMap
    _space: Space
    _mouse_position_history: IMousePositionHistoryManager = Provide[IContainer.mouse_position_history]
    _controlpointmap_manager: IControlPointMapManager = Provide[IContainer.control_point_map_manager]
    _image_manager: IImageManager = Provide[IContainer.image_manager]
    _commandqueue: ICommandQueue
    # _action_command_map: dict[ControlPointAction, ICommand]
    _selected_points: ObservableSet[int]
    cursor_action_map: dict[ControlPointAction, QCursor]
    _setselection: SetSelectionCallable | None
    _last_mouse_press_event_args: QMouseEvent | None = None
    _selection_event_history: dict[SelectionEventKey, SelectionEventData] = {}
    _action_to_command: dict  # type: ignore[type-arg]
    _right_pan_active: bool = False
    _pending_empty_left_click: bool = False
    _left_press_qt: tuple[float, float] | None = None

    log: Logger = logging.Logger("DefaultTransformCommand")

    @property
    def selected_points(self) -> ObservableSet[int]:
        """This is the set of control points that are currently selected.
        Use this property to avoid accidentally replacing the underlying _selected_points object"""
        return self._selected_points

    @selected_points.setter
    def selected_points(self, value: ObservableSet[int]):
        if self._selected_points is not None:
            if self._selected_points is not value:
                raise ValueError("Cannot replace the selected points set, subscribers would be broken")

        self._selected_points = value

    @property
    def search_radius(self) -> float:
        return self.config['control_point_search_radius']

    @property
    def camera(self) -> "pyre.ui.Camera":
        return self._camera

    @property
    def space(self) -> Space:
        return self._space

    @inject
    def __init__(self,
                 parent: QWidget,
                 camera: pyre.ui.Camera,
                 bounds: nornir_imageregistration.Rectangle,
                 space: Space,
                 commandqueue: ICommandQueue,
                 selected_points: ObservableSet[int],
                 # Used to update interested parties of which control points are selected
                 completed_func: StatusChangeCallback | None = None,
                 transform_controller: TransformController = Provide[IContainer.transform_controller],
                 transform_control_point_action_maps=Provide[IContainer.transform_action_map].provider,
                 transform_type_to_action_command_map=Provide[IContainer.action_command_map],
                 ):
        """

        :param parent:
        :param camera:
        :param bounds:
        :param space:
        :param commandqueue: Queue of commands that will execute after this command.
        :param completed_func: Function to call when the command changes state
        :param transform_controller:  The controller for the transform we are manipulating
        :param mouse_position_history: The history of mouse positions
        """
        super().__init__(parent, transform_controller=transform_controller, camera=camera, bounds=bounds,
                         space=space, commandqueue=commandqueue,
                         completed_func=completed_func)

        self.cursor_action_map = _build_default_cursor_action_map()

        self._action_command_map_by_type = transform_type_to_action_command_map
        self._get_transform_action_map_dict = transform_control_point_action_maps
        self._action_to_command = transform_type_to_action_command_map[transform_controller.type]
        self._selection_event_history = {}
        self._commandqueue = commandqueue
        self._space = space
        self._selected_points = selected_points
        self._right_pan_active = False
        self._pending_empty_left_click = False
        self._left_press_qt = None
        transform_action_map_factory = transform_control_point_action_maps()[
            transform_controller.type]

        if isinstance(transform_controller.TransformModel, IControlPoints):
            controlpointmapkey = ControlPointManagerKey(
                transform_controller, space, self._view_type())
            self._controlpointmap = self._controlpointmap_manager.getorcreate(controlpointmapkey)
            self._actionmap = transform_action_map_factory(self._controlpointmap)
        else:
            self._actionmap = transform_action_map_factory()  # type: ignore[call-arg]

        # self._transform_controller.AddOnChangeEventListener(self._on_transform_controller_changed)
  
    # def _on_transform_controller_changed(self, *args, **kwargs):
    #     self._action_command_map = pyre.commands.container_overrides.action_command_map[self._transform_controller.type]

    def execute(self):
        #        self._transform_controller.RemoveOnChangeEventListener(self._on_transform_controller_changed)
        super().execute()

    @property
    def executed(self) -> bool:
        return self._executed

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

    def _get_space_point(self, point_pair: PointPair):
        model = self._transform_controller.TransformModel
        if (
                self._view_type() == ViewType.Composite
                and model is not None
                and not is_rigid_transform(model)
        ):
            return point_pair.target
        return point_pair.source if self.space == Space.Source else point_pair.target

    def _build_selection_event(
        self,
        *,
        source: InputSource,
        input_event: InputEvent,
        modifiers,
        position,
        keycode: int | None = None,
    ) -> SelectionEventData:
        return SelectionEventData(
            camera=self.camera,
            source=source,
            input=input_event,
            modifiers=modifiers,
            position=position,
            keycode=keycode,
            existing_selections=self._selected_points,
        )

    def _dispatch_selection_event(
        self, selection_event_data: SelectionEventData, *, update_cursor: bool = True
    ) -> bool:
        new_command = self.check_for_new_command(selection_event_data)
        if not new_command and update_cursor:
            self._update_cursor_for_possible_actions(selection_event_data)

        return new_command

    def on_key_down(self, event):
        # Update the mouse position history
        point_pair = PointPair(source=self._mouse_position_history[Space.Source],
                               target=self._mouse_position_history[Space.Target])
        selection_event_data = self._build_selection_event(
            source=InputSource.Keyboard,
            input_event=InputEvent.Press,
            modifiers=GetKeyModifiers(event),
            position=self._get_space_point(point_pair),
            keycode=event.key(),
        )
        self._dispatch_selection_event(selection_event_data)

        super().on_key_down(event)

        self._selection_event_history[selection_event_data.eventkey] = selection_event_data
        return

    def on_key_up(self, event):

        # Update the mouse position history
        point_pair = PointPair(source=self._mouse_position_history[Space.Source],
                               target=self._mouse_position_history[Space.Target])
        selection_event_data = self._build_selection_event(
            source=InputSource.Keyboard,
            input_event=InputEvent.Release,
            modifiers=GetKeyModifiers(event),
            position=self._get_space_point(point_pair),
            keycode=event.key(),
        )
        self._dispatch_selection_event(selection_event_data)

        super().on_key_up(event)
        self._selection_event_history[selection_event_data.eventkey] = selection_event_data
        return

    def _sync_camera_geometry(self) -> tuple[int, int]:
        """Align camera pixel geometry with the GL panel before mapping mouse events."""
        width, height = self.parent.size().width(), self.parent.size().height()
        if width > 0 and height > 0:
            self._width, self._height = width, height
            self.camera.window_size = np.array((height, width))
        return width, height

    def _pan_camera_by_cursor_motion(
            self,
            prev_cy: float,
            prev_cx: float,
            cy: float,
            cx: float) -> None:
        """Pan so image content tracks a right-drag between two corrected screen positions."""
        view = self._view_type()
        model = self._transform_controller.TransformModel
        if view == ViewType.Composite and model is not None:
            before = world_point_pair_for_composite_mouse(
                self.camera, self._transform_controller, prev_cy, prev_cx)
            after = world_point_pair_for_composite_mouse(
                self.camera, self._transform_controller, cy, cx)
            if before is not None and after is not None:
                apply_composite_display_pan_delta(
                    self.camera,
                    self._transform_controller,
                    before.target - after.target,
                )
            return
        self.camera.pan_by_cursor_motion(prev_cy, prev_cx, cy, cx)

    def on_mouse_press(self, event: QMouseEvent):
        """Determine the command for the mouse action, if any"""
        self.parent.setFocus()
        width, height = self._sync_camera_geometry()
        cy, cx = self.GetCorrectedMousePosition(event, height)
        self._last_mouse_position = (cy, cx)
        # Arm pan only on press so a move-with-button-before-press cannot use a stale anchor.
        self._right_pan_active = bool(event.buttons() & Qt.MouseButton.RightButton)
        point_pair = self.get_world_positions(event)

        # Update the mouse position history
        self._mouse_position_history[Space.Source] = point_pair.source
        self._mouse_position_history[Space.Target] = point_pair.target

        point = self._get_space_point(point_pair)

        selection_event_data = self._build_selection_event(
            source=InputSource.Mouse,
            input_event=InputEvent.Press,
            modifiers=GetMouseModifiers(event, self._last_mouse_press_event_args),  # type: ignore[arg-type]
            position=point,
        )

        self._selection_event_history[selection_event_data.eventkey] = selection_event_data
        self._pending_empty_left_click = False
        self._left_press_qt = None
        if (
                event.buttons() & Qt.MouseButton.LeftButton
                and ControlPointAction.BOX_SELECT in self._action_to_command
        ):
            scale = 1 / self.camera.scale if self.camera.scale else 1.0
            hits = self._actionmap.find_interactions(point, scale)  # type: ignore[call-arg]
            self._pending_empty_left_click = len(hits) == 0
            pos = event.position()
            self._left_press_qt = (float(pos.x()), float(pos.y()))

        if not self._pending_empty_left_click:
            self._dispatch_selection_event(selection_event_data)

        self._last_mouse_press_event_args = event

    def _point_edit_requires_mesh_conversion(self, action: ControlPointAction) -> bool:
        t = self._transform_controller.type
        if action in (ControlPointAction.CREATE, ControlPointAction.CREATE_REGISTER):
            return t in (TransformType.GRID, TransformType.RIGID)
        if action == ControlPointAction.DELETE:
            return t == TransformType.GRID
        return False

    def _mesh_conversion_prompt(self, action: ControlPointAction) -> tuple[str, str]:
        if action == ControlPointAction.DELETE:
            return (
                "Convert to mesh transform?",
                "Refined grid transforms do not support removing control points in the view.\n\n"
                "Convert this transform to a mesh transform so points can be removed?",
            )
        return (
            "Convert to mesh transform?",
            "This transform type does not support adding control points in the view.\n\n"
            "Convert this transform to a mesh transform so points can be added?",
        )

    def _mesh_conversion_kwargs(self) -> dict:
        kwargs: dict = {}
        try:
            source_image = self._image_manager[ViewType.Source]
            kwargs["source_image_shape"] = source_image.shape
        except Exception:
            pass
        return kwargs

    def _convert_current_transform_to_mesh(self) -> bool:
        current = self._transform_controller.TransformModel
        if current.type == TransformType.MESH:
            return True
        try:
            converted = ConvertTransform(current, TransformType.MESH, **self._mesh_conversion_kwargs())
            self._transform_controller.TransformModel = converted
            return True
        except Exception as e:
            self.log.exception("Convert to mesh transform failed")
            QMessageBox.warning(
                self.parent,
                "Convert transform",
                f"Unable to convert transform to mesh: {e}",
            )
            return False

    def _rebind_maps_for_current_transform_type(self) -> None:
        tc = self._transform_controller
        self._action_to_command = self._action_command_map_by_type[tc.type]
        map_factory = self._get_transform_action_map_dict()[tc.type]
        if isinstance(tc.TransformModel, IControlPoints):
            controlpointmapkey = ControlPointManagerKey(tc, self._space, self._view_type())
            self._controlpointmap = self._controlpointmap_manager.getorcreate(controlpointmapkey)
            self._actionmap = map_factory(self._controlpointmap)
        else:
            self._actionmap = map_factory()  # type: ignore[call-arg]

    def check_for_new_command(self, selection_event_data: SelectionEventData) -> bool:
        """:return: True if a new command was created"""
        if self.status != pyre.CommandStatus.Active:
            return False

        new_action = self._actionmap.get_action(selection_event_data)

        if self._point_edit_requires_mesh_conversion(new_action.action):
            title, message = self._mesh_conversion_prompt(new_action.action)
            reply = QMessageBox.question(
                self.parent,
                title,
                message,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return False
            if not self._convert_current_transform_to_mesh():
                return False
            self._rebind_maps_for_current_transform_type()
            new_action = self._actionmap.get_action(selection_event_data)

        if blocks_layer_translate_action(
                self._transform_controller.type, self.space, new_action.action, self._view_type()):
            return False

        if blocks_control_point_translate_action(
                self._transform_controller.TransformModel,
                self.space,
                new_action.action,
                self._view_type()):
            return False

        if new_action.action not in self._action_to_command:
            self.log.error(
                f'Action {new_action.action} not in action to command map for {self._transform_controller.type} transforms')
            return False

            # raise ValueError(
            #     f'Action {new_action.action} not in action to command map for {self._transform_controller.type} transforms')
        if new_action.action is not ControlPointAction.NONE:
            # self.ensure_mouse_point_is_in_selection(selection_event_data)
            # command_factory = self._transform_type_to_command_action_map[self.transform_controller.type]

            try:
                command_kwargs: dict = {}
                if new_action.action in (ControlPointAction.BOX_SELECT, ControlPointAction.LASSO_SELECT):
                    command_kwargs['region_origin_qt'] = self._left_press_qt
                    command_kwargs['set_operation'] = (
                        SetOperation.Union if selection_event_data.IsShiftPressed else SetOperation.Replace
                    )
                new_command = self._action_to_command[new_action.action](parent=self.parent,
                                                                         camera=self.camera,
                                                                         bounds=self._bounds,
                                                                         space=self.space,
                                                                         commandqueue=self._commandqueue,
                                                                         selected_points=self._selected_points,
                                                                         command_points=new_action.point_indicies,
                                                                         **command_kwargs)
                self._commandqueue.put(new_command)
                self.execute()
                return True
            except RequiresSelectionError:
                self.log.error(
                    f"No control points selected for {new_action.action} command {self._action_to_command[new_action.action]}")
                pass

        return False

    def ensure_mouse_point_is_in_selection(self, selection_event_data: SelectionEventData):
        """For a command we want to make sure that the point under the mouse is passed with the selected points.
        This was needed for commands triggered by the right-mouse button that did not cause the selection check"""
        new_selections = self._actionmap.find_interactions(selection_event_data.position,
                                                           1 / self.camera.scale)  # type: ignore[call-arg]
        self.selected_points.update(new_selections)

    def on_mouse_motion(self, event: QMouseEvent):
        _, height = self._sync_camera_geometry()
        cy, cx = self.GetCorrectedMousePosition(event, height)
        if self._right_pan_active and (event.buttons() & Qt.MouseButton.RightButton):
            if self._last_mouse_position is not None:
                prev_cy, prev_cx = self._last_mouse_position
                if prev_cy != cy or prev_cx != cx:
                    self._pan_camera_by_cursor_motion(prev_cy, prev_cx, cy, cx)
            self._last_mouse_position = (cy, cx)
        elif not (event.buttons() & Qt.MouseButton.RightButton):
            self._right_pan_active = False
            self._last_mouse_position = (cy, cx)

        point_pair = self.get_world_positions(event)
        try:
            point = self._get_space_point(point_pair)

            selection_event_data = self._build_selection_event(
                source=InputSource.Mouse,
                input_event=InputEvent.Drag,
                modifiers=GetMouseModifiers(event, self._last_mouse_press_event_args),  # type: ignore[arg-type]
                position=point,
            )

            self._selection_event_history[selection_event_data.eventkey] = selection_event_data
            if self._pending_empty_left_click and (event.buttons() & Qt.MouseButton.LeftButton):
                dx = 0.0
                dy = 0.0
                if self._left_press_qt is not None:
                    pos = event.position()
                    dx = float(pos.x()) - self._left_press_qt[0]
                    dy = float(pos.y()) - self._left_press_qt[1]
                    if (dx * dx + dy * dy) < REGION_DRAG_THRESHOLD_PX * REGION_DRAG_THRESHOLD_PX:
                        return
                self._pending_empty_left_click = False

            # Check for command, if there is no command, scroll the camera
            new_command = self._dispatch_selection_event(selection_event_data, update_cursor=False)
            if new_command:
                return

            if not (event.buttons() & Qt.MouseButton.RightButton) and not (
                    event.buttons() & Qt.MouseButton.LeftButton):
                self._update_cursor_for_possible_actions(selection_event_data)

        finally:
            # Ensure we update the mouse position history
            self._mouse_position_history[Space.Source] = point_pair.source
            self._mouse_position_history[Space.Target] = point_pair.target
            self._last_mouse_press_event_args = event
        return

    def _update_cursor_for_possible_actions(self, selection_event_data: SelectionEventData):
        # No button is down,
        # TODO: Update help strings based on the possible actions
        possible_actions = self._actionmap.get_possible_actions(selection_event_data)
        # print(f'possible actions: {possible_actions}')
        if possible_actions.action in self.cursor_action_map:
            cursor = self.cursor_action_map[possible_actions.action]
            self.parent.setCursor(cursor)

    def on_mouse_release(self, event):
        self._right_pan_active = False
        self._pending_empty_left_click = False
        _, height = self._sync_camera_geometry()
        cy, cx = self.GetCorrectedMousePosition(event, height)
        self._last_mouse_position = (cy, cx)
        point_pair = self.get_world_positions(event)
        point = self._get_space_point(point_pair)

        #        last_selection = self._get_last_event(InputSource.Mouse, InputEvent.Press)

        selection_event_data = self._build_selection_event(
            source=InputSource.Mouse,
            input_event=InputEvent.Release,
            modifiers=GetMouseModifiers(event, self._last_mouse_press_event_args),  # type: ignore[arg-type]
            position=point,
        )
        self._dispatch_selection_event(selection_event_data)

        self._last_mouse_press_event_args = event
        self._selection_event_history[selection_event_data.eventkey] = selection_event_data
        return
