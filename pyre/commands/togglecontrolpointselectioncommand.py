from __future__ import annotations

import enum

from dependency_injector.providers import Provider, Configuration
from dependency_injector.wiring import inject, Provide
import numpy as np
from numpy._typing import NDArray
import wx
from pyre.observable import ObservableSet, ObservedAction
from pyre.observable import SetOperation

import nornir_imageregistration
import pyre
from pyre import Space
from pyre.command_interfaces import StatusChangeCallback
from pyre.commands import InstantCommandBase, UICommandBase, NavigationCommandBase
from pyre.interfaces.managers import ICommandQueue, IMousePositionHistoryManager, ControlPointManagerKey, \
    IControlPointMapManager
from pyre.interfaces.controlpointselection import SetSelectionCallable
from pyre.container import IContainer


class ToggleControlPointSelectionCommand(InstantCommandBase):
    """
    This command doesn't subscribe to input events by default and
    simply executes a lambda function when activated
    """
    _selection_set: ObservableSet[int]  # The indices of the selected points

    # _controlpointmap_manager: IControlPointMapManager = Provide[IContainer.controlpointmap_manager]
    # _mouse_position_history: IMousePositionHistoryManager = Provide[IContainer.mouse_position_history]
    # _config: Configuration = Provide[IContainer.config]
    _command_action_points: set[int]
    _set_operation: SetOperation

    @inject
    def __init__(self,
                 parent: wx.Window,
                 selected_points: ObservableSet[int],  # The indices of the selected points
                 command_points: set[int],  # Points under mouse when command was triggered
                 space: Space,  # Space we are moving the points in, source or target side
                 set_operation: SetOperation,
                 completed_func: StatusChangeCallback = None,

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
        super().__init__(completed_func)

        self._selection_set = selected_points
        self._set_operation = set_operation

        self._command_points = command_points

        # controlpointmapkey = ControlPointManagerKey(transform_controller, space)
        # self._controlpointmap = self._controlpointmap_manager.getorcreate(controlpointmapkey)
        # self._mouse_position = self._mouse_position_history[space]
        #
        # change_index = self._controlpointmap.find_nearest_within(self._mouse_position,
        #                                                    self._config['control_point_search_radius'])

    def __str__(self):
        return "ToggleControlPointSelectionCommand"

    def can_execute(self) -> bool:
        return True

    def cancel(self):
        super().cancel()
        return

    def execute(self):
        # Check if shift is pressed to add to a selection

        if self._set_operation == SetOperation.Union:
            self._selection_set.update(self._command_points)
        elif self._set_operation == SetOperation.Replace:
            self._selection_set.clear()
            self._selection_set.update(self._command_points)
        elif self._set_operation == SetOperation.SymmetricDifference:
            self._selection_set ^= self._command_points
        elif self._set_operation == SetOperation.Intersection:
            self._selection_set.intersection_update(self._command_points)
        else:
            raise ValueError(f"Unknown SetOperation {self._set_operation}")

        # if selection_event_data.IsShiftPressed:
        #     self._selection_set ^= self._command_action_points
        # else:
        #     # Clear the existing selection and set the new selection
        #     self._selection_set.clear()
        #     self._selection_set.update(self._command_action_points)

        super().execute()

    def activate(self):
        super().activate()
        self.execute()
