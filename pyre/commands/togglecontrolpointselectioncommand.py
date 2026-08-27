from __future__ import annotations

import enum

from dependency_injector.providers import Provider, Configuration
from dependency_injector.wiring import Provide
import numpy as np
from numpy.typing import NDArray
from PyQt6.QtWidgets import QWidget
from pyre.observable import ObservableSet, ObservedAction
from pyre.observable import SetOperation

import nornir_imageregistration
import pyre
from pyre import Space
from pyre.interfaces import StatusChangeCallback
from pyre.commands import InstantCommandBase, UICommandBase, NavigationCommandBase
from pyre.interfaces.managers import ICommandQueue, IMousePositionHistoryManager, ControlPointManagerKey, \
    IControlPointMapManager
from pyre.interfaces.controlpointselection import SetSelectionCallable
from pyre.container import IContainer


def apply_shift_region_selection(
        selection_set: ObservableSet[int],
        hits: set[int] | None,
) -> None:
    """Shift+region: add hits unless every hit is already selected, then remove that group."""
    points = set() if hits is None else set(hits)
    if not points:
        return
    if points <= selection_set:
        apply_selection_set_operation(selection_set, points, SetOperation.Difference)
        return
    apply_selection_set_operation(selection_set, points, SetOperation.Union)


def apply_selection_set_operation(
        selection_set: ObservableSet[int],
        command_points: set[int] | None,
        set_operation: SetOperation,
) -> None:
    """Apply ``set_operation`` between ``selection_set`` and ``command_points`` in place."""
    points = set() if command_points is None else set(command_points)
    if set_operation == SetOperation.Union:
        selection_set.update(points)
    elif set_operation == SetOperation.Replace:
        selection_set.clear()
        selection_set.update(points)
    elif set_operation == SetOperation.SymmetricDifference:
        selection_set ^= points
    elif set_operation == SetOperation.Intersection:
        selection_set.intersection_update(points)
    elif set_operation == SetOperation.Difference:
        selection_set.difference_update(points)
    elif set_operation == SetOperation.AddOrRemoveGroup:
        apply_shift_region_selection(selection_set, points)
    else:
        raise ValueError(f"Unknown SetOperation {set_operation}")


class ToggleControlPointSelectionCommand(InstantCommandBase):
    """
    This command doesn't subscribe to input events by default and
    simply executes a lambda function when activated
    """
    _selection_set: ObservableSet[int]  # The indices of the selected points

    # _controlpointmap_manager: IControlPointMapManager = Provide[IContainer.control_point_map_manager]
    # _mouse_position_history: IMousePositionHistoryManager = Provide[IContainer.mouse_position_history]
    # _config: Configuration = Provide[IContainer.config]
    _command_action_points: set[int]
    _set_operation: SetOperation

    def __init__(self,
                 parent: QWidget,
                 selected_points: ObservableSet[int],  # The indices of the selected points
                 command_points: set[int],  # Points under mouse when command was triggered
                 space: Space,  # Space we are moving the points in, source or target side
                 set_operation: SetOperation,
                 completed_func: StatusChangeCallback | None = None,

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
        apply_selection_set_operation(self._selection_set, self._command_points, self._set_operation)
        super().execute()

    def activate(self):
        super().activate()
        self.execute()
