from __future__ import annotations

from dependency_injector.wiring import inject, Provide
import numpy as np
from numpy._typing import NDArray
import wx

import nornir_imageregistration
import pyre
from pyre.observable import ObservableSet, ObservedAction
from pyre import Space
from pyre.command_interfaces import StatusChangeCallback
from pyre.commands import InstantCommandBase, NavigationCommandBase
from pyre.commands.commandexceptions import RequiresSelectionError
from pyre.interfaces.managers import ICommandQueue, IMousePositionHistoryManager
from pyre.container import IContainer
from pyre.controllers import TransformController


class CallControlPointToMouseCommand(InstantCommandBase):
    """This command deletes a selection of control points"""

    _selected_points: ObservableSet[int]  # The indices of the selected points
    _original_points: NDArray[[2, ], np.floating]
    _transform_controller: TransformController

    _space: Space
    _translate_origin: NDArray[float]
    _original_points: NDArray[[2, ], np.floating]

    _mouse_position_history: IMousePositionHistoryManager = Provide[IContainer.mouse_position_history]
    _mouse_position: NDArray[float] = None
    _selected_point: int

    @inject
    def __init__(self,
                 space: Space,
                 selected_points: ObservableSet[int],  # The indices of the selected points
                 command_points: set[int],  # Points under mouse when command was triggered
                 completed_func: StatusChangeCallback = None,
                 transform_controller: pyre.viewmodels.TransformController = Provide[IContainer.transform_controller],
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
        super().__init__(completed_func=completed_func)
        self._transform_controller = transform_controller
        self._mouse_position = self._mouse_position_history[space]
        self._space = space

        self._selected_points = selected_points
        self._selected_points.update(command_points)
        if len(self._selected_points) != 1:
            raise RequiresSelectionError("Select a single point to move")

        self._selected_point = self._selected_points.__iter__().__next__()

        self._original_points = transform_controller.points

    def __str__(self):
        return "CallControlPointToMouseCommand"

    def can_execute(self) -> bool:
        return True

    def cancel(self):
        super().cancel()
        return

    def execute(self):
        indicies_to_delete = list(self._selected_points)
        self._transform_controller.SetPoint(self._selected_point,
                                            self._mouse_position[1],
                                            self._mouse_position[0],
                                            self._space)
        super().execute()

    def activate(self):
        super().activate()
        self.execute()
