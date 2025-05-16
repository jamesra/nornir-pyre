from __future__ import annotations

from dependency_injector.wiring import inject, Provide
import numpy as np
from numpy._typing import NDArray
import wx
from pyre.observable import ObservableSet, ObservedAction

import nornir_imageregistration
import pyre
from pyre import Space
from pyre.command_interfaces import StatusChangeCallback
from pyre.commands import NavigationCommandBase, InstantCommandBase
from pyre.commands.commandexceptions import RequiresSelectionError
from pyre.interfaces.managers import ICommandQueue, IMousePositionHistoryManager
from pyre.interfaces.controlpointselection import SetSelectionCallable
from pyre.container import IContainer
from pyre.controllers import TransformController


class DeleteControlPointCommand(InstantCommandBase):
    """This command deletes a selection of control points"""

    _selected_points: ObservableSet[int]  # The indices of the selected points
    _original_points: NDArray[[2, ], np.floating]
    _transform_controller: TransformController

    @inject
    def __init__(self,
                 selected_points: ObservableSet[int],  # The indices of the selected points
                 command_points: set[int],  # Points under mouse when command was triggered
                 completed_func: StatusChangeCallback = None,
                 transform_controller: TransformController = Provide[IContainer.transform_controller],
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
        self._selected_points = selected_points
        self._selected_points.update(command_points)
        self._transform_controller = transform_controller
        if len(selected_points) == 0:
            raise RequiresSelectionError()

        self._original_points = transform_controller.points

    def __str__(self):
        return "DeleteControlPointCommand"

    def can_execute(self) -> bool:
        return True

    def cancel(self):
        super().cancel()
        return

    def execute(self):
        indicies_to_delete = list(self._selected_points)
        self._selected_points.clear()
        self._transform_controller.TryDeletePoints(indicies_to_delete)
        super().execute()

    def activate(self):
        super().activate()
        self.execute()
