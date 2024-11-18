from __future__ import annotations

import logging

import wx
from dependency_injector.wiring import Provide, inject
from dependency_injector.providers import Dict, Factory
from logging import Logger

import nornir_imageregistration
from nornir_imageregistration.transforms import IControlPointEdit, IControlPoints
from pyre.commands.commandexceptions import RequiresSelectionError
from pyre.interfaces import ControlPointAction, SetSelectionCallable
from pyre.observable import ObservableSet
from pyre.selection_event_data import InputEvent, SelectionEventData, InputSource, PointPair, SelectionEventKey
from pyre.command_interfaces import ICommand, IInstantCommand
from pyre.command_interfaces import StatusChangeCallback
from pyre.interfaces.managers import ICommandQueue, IMousePositionHistoryManager, IControlPointMapManager, \
    IControlPointActionMap, ControlPointManagerKey
from pyre.controllers import TransformController
import pyre.views.pointview
from pyre.space import Space
from pyre.commands.navigationcommandbase import NavigationCommandBase
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
    _actionmap: IControlPointActionMap
    _space: Space
    _mouse_position_history: IMousePositionHistoryManager = Provide[IContainer.mouse_position_history]
    _controlpointmap_manager: IControlPointMapManager = Provide[IContainer.controlpointmap_manager]
    _commandqueue: ICommandQueue
    # _action_command_map: dict[ControlPointAction, ICommand]
    _selected_points: ObservableSet[int]
    cursor_action_map: dict[ControlPointAction, wx.Cursor]
    _setselection: SetSelectionCallable | None
    _last_mouse_press_event_args: wx.MouseEvent | None = None
    _selection_event_history: dict[SelectionEventKey, SelectionEventData] = {}
    _action_to_command: Dict[ControlPointAction, Factory]

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
                 parent: wx.Window,
                 camera: pyre.ui.Camera,
                 bounds: nornir_imageregistration.Rectangle,
                 space: Space,
                 commandqueue: ICommandQueue,
                 selected_points: ObservableSet[int],
                 # Used to update interested parties of which control points are selected
                 completed_func: StatusChangeCallback | None = None,
                 transform_controller: TransformController = Provide[IContainer.transform_controller],
                 transform_control_point_action_maps=Provide[IContainer.transform_action_map].provider,
                 transform_type_to_action_command_map=Provide[IContainer.action_command_map]
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

        self._action_to_command = transform_type_to_action_command_map[transform_controller.type]
        # self._action_command_map = pyre.commands.container_overrides.action_command_map[transform_controller.type]
        self._selection_event_history = {}
        # self._action_command_map = action_command_map[transform_controller.type]
        self._commandqueue = commandqueue
        self._executed = False
        self._space = space
        self._selected_points = selected_points
        transform_action_map_factory = transform_control_point_action_maps()[
            transform_controller.type]

        if isinstance(transform_controller.TransformModel, IControlPoints):
            controlpointmapkey = ControlPointManagerKey(transform_controller, space)
            print(f'Key: {controlpointmapkey} Space: {space}')

            self._controlpointmap = DefaultTransformCommand._controlpointmap_manager.getorcreate(controlpointmapkey)
            self._actionmap = transform_action_map_factory(self._controlpointmap)
        else:
            self._actionmap = transform_action_map_factory()

        # self._transform_controller.AddOnChangeEventListener(self._on_transform_controller_changed)

    # def _on_transform_controller_changed(self, *args, **kwargs):
    #     self._action_command_map = pyre.commands.container_overrides.action_command_map[self._transform_controller.type]

    def execute(self):
        #        self._transform_controller.RemoveOnChangeEventListener(self._on_transform_controller_changed)
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

    def _get_last_event(self, input_source: InputSource, input_event: InputEvent) -> SelectionEventData | None:
        key = SelectionEventKey(input_source, input_event)
        return self._selection_event_history.get(key, None)

    def on_key_down(self, event):
        # Update the mouse position history
        point_pair = PointPair(source=self._mouse_position_history[Space.Source],
                               target=self._mouse_position_history[Space.Target])
        point = point_pair.source if self.space == Space.Source else point_pair.target
        selection_event_data = SelectionEventData(camera=self.camera,
                                                  source=InputSource.Keyboard,
                                                  input=InputEvent.Press,
                                                  modifiers=GetKeyModifiers(event),
                                                  position=point,
                                                  keycode=event.GetKeyCode(),
                                                  existing_selections=self._selected_points)
        new_command = self.check_for_new_command(selection_event_data)
        if not new_command:
            self._update_cursor_for_possible_actions(selection_event_data)

        super().on_key_down(event)

        self._selection_event_history[selection_event_data.eventkey] = selection_event_data
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
                                                  position=point,
                                                  keycode=event.GetKeyCode(),
                                                  existing_selections=self._selected_points)
        new_command = self.check_for_new_command(selection_event_data)
        if not new_command:
            self._update_cursor_for_possible_actions(selection_event_data)

        super().on_key_up(event)
        self._selection_event_history[selection_event_data.eventkey] = selection_event_data
        return

    def on_mouse_press(self, event: wx.MouseEvent):
        """Determine the command for the mouse action, if any"""
        self.parent.SetFocus()
        point_pair = self.get_world_positions(event)

        # Update the mouse position history
        self._mouse_position_history[Space.Source] = point_pair.source
        self._mouse_position_history[Space.Target] = point_pair.target

        point = point_pair.source if self.space == Space.Source else point_pair.target

        last_selection_event = self._get_last_event(InputSource.Mouse, InputEvent.Release)
        selection_event_data = SelectionEventData(camera=self.camera,
                                                  source=InputSource.Mouse,
                                                  input=InputEvent.Press,
                                                  modifiers=GetMouseModifiers(event, self._last_mouse_press_event_args),
                                                  position=point,
                                                  existing_selections=self._selected_points)

        self._selection_event_history[selection_event_data.eventkey] = selection_event_data
        new_command = self.check_for_new_command(selection_event_data)
        if not new_command:
            self._update_cursor_for_possible_actions(selection_event_data)

        self._last_mouse_press_event_args = event.Clone()

    def check_for_new_command(self, selection_event_data: SelectionEventData) -> bool:
        """:return: True if a new command was created"""
        new_action = self._actionmap.get_action(selection_event_data)
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
                new_command = self._action_to_command[new_action.action](parent=self.parent,
                                                                         camera=self.camera,
                                                                         bounds=self._bounds,
                                                                         space=self.space,
                                                                         commandqueue=self._commandqueue,
                                                                         selected_points=self._selected_points,
                                                                         command_points=new_action.point_indicies)
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
                                                           1 / self.camera.scale)
        self.selected_points.update(new_selections)

    def on_mouse_motion(self, event: wx.MouseEvent):
        point_pair = self.get_world_positions(event)
        try:
            point = point_pair.source if self.space == Space.Source else point_pair.target

            selection_event_data = SelectionEventData(camera=self.camera,
                                                      source=InputSource.Mouse,
                                                      input=InputEvent.Drag,
                                                      modifiers=GetMouseModifiers(event,
                                                                                  self._last_mouse_press_event_args),
                                                      position=point,
                                                      existing_selections=self._selected_points)

            self._selection_event_history[selection_event_data.eventkey] = selection_event_data
            # Check for command, if there is no command, scroll the camera
            new_command = self.check_for_new_command(selection_event_data)
            if new_command:
                return

            # Todo: Make these commands as well
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
            self._last_mouse_press_event_args = event.Clone()
        return

    def _update_cursor_for_possible_actions(self, selection_event_data: SelectionEventData):
        # No button is down,
        # TODO: Update help strings based on the possible actions
        possible_actions = self._actionmap.get_possible_actions(selection_event_data)
        # print(f'possible actions: {possible_actions}')
        if possible_actions.action in self.cursor_action_map:
            cursor = self.cursor_action_map[possible_actions.action]
            wx.SetCursor(cursor)

    def on_mouse_release(self, event):
        point_pair = self.get_world_positions(event)
        point = point_pair.source if self.space == Space.Source else point_pair.target

        #        last_selection = self._get_last_event(InputSource.Mouse, InputEvent.Press)

        selection_event_data = SelectionEventData(camera=self.camera,
                                                  source=InputSource.Mouse,
                                                  input=InputEvent.Release,
                                                  position=point,
                                                  modifiers=GetMouseModifiers(event, self._last_mouse_press_event_args),
                                                  existing_selections=self._selected_points)
        new_command = self.check_for_new_command(selection_event_data)
        if not new_command:
            self._update_cursor_for_possible_actions(selection_event_data)

        self._last_mouse_press_event_args = event.Clone()
        self._selection_event_history[selection_event_data.eventkey] = selection_event_data
        return
