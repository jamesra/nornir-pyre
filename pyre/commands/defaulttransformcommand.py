from __future__ import annotations

import wx
from typing import Callable
from dependency_injector.wiring import Provide, inject
from dependency_injector.providers import Dict, Factory

import nornir_imageregistration
from pyre.interfaces import ControlPointAction, SetSelectionCallable
from pyre.selection_event_data import InputEvent, InputModifiers, SelectionEventData, InputSource, PointPair
from pyre.commands.commandbase import ICommand
from pyre.command_interfaces import StatusChangeCallback
from pyre.interfaces.managers import ICommandQueue, IMousePositionHistoryManager, IControlPointMapManager, \
    IControlPointActionMap, ControlPointManagerKey
from pyre.controllers import TransformController
import pyre.views.pointview
from pyre.space import Space
from pyre.commands.navigationcommandbase import NavigationCommandBase
from pyre.state.managers.controlpointcommandmanager import ControlPointActionMap
from pyre.container import IContainer
from pyre.commands.extensions import GetKeyModifiers, GetMouseModifiers
import pyre.ui


class DefaultTransformCommand(NavigationCommandBase):
    """
    Supports:
     1. Navigating around the view of the images.
     2. Selecting control points
    """
    _executed: bool | None = None

    config = Provide[IContainer.config]

    _controlpointmap: pyre.viewmodels.ControlPointMap
    _controlpointactionmap: IControlPointActionMap

    _space: Space
    _mouse_position_history: IMousePositionHistoryManager

    _controlpointmap_manager: IControlPointMapManager = Provide[IContainer.controlpointmap_manager]

    _commandqueue: ICommandQueue

    _action_command_map: dict[ControlPointAction, ICommand]

    _selected_points: set[int] = set()

    cursor_action_map: dict[ControlPointAction, wx.Cursor]

    _setselection: SetSelectionCallable | None

    # _action_command_dp_map: ControlPointActionCommandMapType

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
                 parent: wx.Window,
                 camera: pyre.ui.Camera,
                 bounds: nornir_imageregistration.Rectangle,
                 space: Space,
                 commandqueue: ICommandQueue,
                 setselection: SetSelectionCallable | None,
                 # Used to update interested parties of which control points are selected
                 completed_func: StatusChangeCallback | None = None,
                 transform_controller: TransformController = Provide[IContainer.transform_controller],
                 mouse_position_history: IMousePositionHistoryManager = Provide[IContainer.mouse_position_history]
                 ):
        super().__init__(parent, transform_controller=transform_controller, camera=camera, bounds=bounds,
                         space=space, commandqueue=commandqueue,
                         completed_func=completed_func)

        self.cursor_action_map = {
            ControlPointAction.NONE: wx.Cursor(wx.CURSOR_DEFAULT),
            ControlPointAction.CREATE: wx.Cursor(wx.CURSOR_PENCIL),
            ControlPointAction.DELETE: wx.Cursor(wx.CURSOR_NO_ENTRY),
            ControlPointAction.TRANSLATE: wx.Cursor(wx.CURSOR_HAND),
            ControlPointAction.REGISTER: wx.Cursor(wx.CURSOR_MAGNIFIER),
            ControlPointAction.TRANSLATE | ControlPointAction.REGISTER: wx.Cursor(wx.CURSOR_HAND),
            ControlPointAction.DELETE | ControlPointAction.TRANSLATE | ControlPointAction.REGISTER: wx.Cursor(
                wx.CURSOR_HAND),
        }
        self._setselection = setselection
        self._action_command_map = pyre.commands.container_overrides.action_command_map[transform_controller.type]
        self._commandqueue = commandqueue
        self._executed = False
        self._space = space
        self._mouse_position_history = mouse_position_history
        controlpointmapkey = ControlPointManagerKey(transform_controller, space)

        self._controlpointmap = DefaultTransformCommand._controlpointmap_manager.getorcreate(controlpointmapkey)
        self._controlpointactionmap = ControlPointActionMap(self._controlpointmap)

        self._transform_controller.AddOnChangeEventListener(self._on_transform_controller_changed)

    def _on_transform_controller_changed(self, *args, **kwargs):
        self._action_command_map = pyre.commands.container_overrides.action_command_map[self._transform_controller.type]

    def execute(self):
        self._transform_controller.RemoveOnChangeEventListener(self._on_transform_controller_changed)
        super().execute()

    @property
    def executed(self) -> bool:
        return self._executed

    @property
    def SelectionMaxDistance(self) -> float:
        """How close we need to be to a control point to select it"""
        selection_max_distance = (float(self.camera.visible_world_height) / float(self.height)) * self.search_radius
        if selection_max_distance < self.search_radius:
            selection_max_distance = self.search_radius

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

    def on_key_down(self, event):
        # Update the mouse position history
        point_pair = PointPair(source=self._mouse_position_history[Space.Source],
                               target=self._mouse_position_history[Space.Target])
        point = point_pair.source if self.space == Space.Source else point_pair.target
        selection_event_data = SelectionEventData(camera=self.camera,
                                                  source=InputSource.Keyboard,
                                                  input=InputEvent.Press,
                                                  modifiers=GetKeyModifiers(event),
                                                  position=point)
        self._update_cursor_for_possible_actions(selection_event_data)
        return

    def on_key_up(self, event):

        # Update the mouse position history
        point_pair = PointPair(source=self._mouse_position_history[Space.Source],
                               target=self._mouse_position_history[Space.Target])
        point = point_pair.source if self.space == Space.Source else point_pair.target
        selection_event_data = SelectionEventData(camera=self.camera,
                                                  source=InputSource.Keyboard,
                                                  input=InputEvent.Release,
                                                  modifiers=GetKeyModifiers(event),
                                                  position=point)
        self._update_cursor_for_possible_actions(selection_event_data)
        return

    def on_mouse_press(self, event: wx.MouseEvent):
        """Determine the command for the mouse action, if any"""
        point_pair = self.get_world_positions(event)

        # Update the mouse position history
        self._mouse_position_history[Space.Source] = point_pair.source
        self._mouse_position_history[Space.Target] = point_pair.target

        point = point_pair.source if self.space == Space.Source else point_pair.target
        selection_event_data = SelectionEventData(camera=self.camera,
                                                  source=InputSource.Mouse,
                                                  input=InputEvent.Press,
                                                  modifiers=GetMouseModifiers(event),
                                                  position=point)

        if event.LeftIsDown():
            self.update_selection(selection_event_data)

        new_command = self._controlpointactionmap.get_action(selection_event_data)
        if new_command is not ControlPointAction.NONE and new_command in self._action_command_map:
            if (self._selected_points is None or len(
                    self._selected_points) == 0) and new_command != ControlPointAction.CREATE:
                raise ValueError("No control points selected")

            new_command = self._action_command_map[new_command](parent=self.parent,
                                                                camera=self.camera,
                                                                bounds=self._bounds,
                                                                space=self.space,
                                                                commandqueue=self._commandqueue,
                                                                selected_points=self._selected_points)
            self._commandqueue.put(new_command)
            self.execute()
            return

        # Do we create a new control point?
        return

    def update_selection(self, selection_event_data: SelectionEventData):
        # Update the selection based on the current mouse position
        new_selections = self._controlpointactionmap.find_interactions(selection_event_data.position,
                                                                       1 / self.camera.scale)

        # Check if shift is pressed to add to a selection
        if selection_event_data.IsShiftPressed:
            self._selected_points ^= new_selections
        else:
            self._selected_points = new_selections

        if self._setselection is not None:
            self._setselection(self._selected_points)

    def on_mouse_motion(self, event: wx.MouseEvent):
        point_pair = self.get_world_positions(event)
        try:
            point = point_pair.source if self.space == Space.Source else point_pair.target

            selection_event_data = SelectionEventData(camera=self.camera,
                                                      source=InputSource.Mouse,
                                                      input=InputEvent.Drag,
                                                      modifiers=GetMouseModifiers(event),
                                                      position=point)
            # Check for command, if there is no command, scroll the camera

            if event.LeftIsDown():
                # Draw a rectangle to select point
                pass
            elif event.RightIsDown():
                old_point = self._mouse_position_history[self.space]
                dy, dx = self._mouse_position_history[self.space] - point
                print(f'x:{point[1]} y:{point[0]} hx:{old_point[1]} hy:{old_point[0]} dx:{dx} dy:{dy}')
                self.camera.translate((dy, dx))

                # Update the point pair to account for camera motion
                point_pair = self.get_world_positions(event)
            else:
                self._update_cursor_for_possible_actions(selection_event_data)

        finally:
            # Ensure we update the mouse position history
            self._mouse_position_history[Space.Source] = point_pair.source
            self._mouse_position_history[Space.Target] = point_pair.target

        return

    def _update_cursor_for_possible_actions(self, selection_event_data: SelectionEventData):
        # No button is down,
        # TODO: Update help strings based on the possible actions
        possible_actions = self._controlpointactionmap.get_possible_actions(selection_event_data)
        # print(f'possible actions: {possible_actions}')
        if possible_actions in self.cursor_action_map:
            cursor = self.cursor_action_map[possible_actions]
            wx.SetCursor(cursor)

    def on_mouse_release(self, event):
        point_pair = self.get_world_positions(event)
        point = point_pair.source if self.space == Space.Source else point_pair.target

        selection_event_data = SelectionEventData(camera=self.camera,
                                                  source=InputSource.Mouse,
                                                  input=InputEvent.Release,
                                                  position=point,
                                                  modifiers=GetMouseModifiers(event))

        self._update_cursor_for_possible_actions(selection_event_data)
        return
