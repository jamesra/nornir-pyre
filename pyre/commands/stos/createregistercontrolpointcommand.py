from __future__ import annotations

from dependency_injector.wiring import inject, Provide
from dependency_injector.providers import Configuration
import numpy as np
from numpy.typing import NDArray
from PyQt6.QtCore import QTimer

import nornir_imageregistration
import pyre
from pyre.observable import ObservableSet, ObservedAction
from pyre import Space
from pyre.interfaces import StatusChangeCallback, ICommand
from pyre.commands import InstantCommandBase
from pyre.interfaces.managers import ICommandQueue, IMousePositionHistoryManager
from pyre.container import IContainer
from pyre.selection_event_data import InputEvent, InputModifiers, SelectionEventData, InputSource, PointPair
from pyre.commands.stos.point_coords import control_point_row_from_pair


class CreateRegisterControlPointCommand(InstantCommandBase):
    """Add a control point at the current mouse pair and queue registration for that point."""

    _space: Space
    _new_point_position: PointPair
    _selected_points: ObservableSet[int]  # The indices of the selected points

    _mouse_position_history: IMousePositionHistoryManager = Provide[IContainer.mouse_position_history]
    _original_points: NDArray[np.floating]
    _left_mouse_down: bool = False
    _transform_controller: "pyre.viewmodels.TransformController"  # type: ignore[name-defined]
    _commandqueue: ICommandQueue

    _source_image: str
    _target_image: str

    @inject
    def __init__(self,
                 commandqueue: ICommandQueue,
                 selected_points: ObservableSet[int],  # The indices of the selected points
                 source_image: str,
                 target_image: str,
                 completed_func: StatusChangeCallback | None = None,
                 transform_controller: "pyre.viewmodels.TransformController" = Provide[IContainer.transform_controller],  # type: ignore[attr-defined]
                 config: Configuration = Provide[IContainer.config],
                 **kwargs):
        super().__init__(completed_func=completed_func)  # type: ignore[arg-type]
        source_position = self._mouse_position_history[Space.Source]
        target_position = self._mouse_position_history[Space.Target]

        self._config = config
        self._source_image = source_image
        self._target_image = target_image
        self._selected_points = selected_points
        self._transform_controller = transform_controller
        self._commandqueue = commandqueue
        self._new_point_position = PointPair(source=source_position, target=target_position)
        self._original_points = transform_controller.points

    def on_activate(self):
        QTimer.singleShot(0, self.queue_registration_command)

    def __str__(self):
        return "CreateRegisterControlPointCommand"

    def can_execute(self) -> bool:
        return True

    def cancel(self):
        super().cancel()
        return

    def queue_registration_command(self):

        point = self._new_point_position
        newpoint = control_point_row_from_pair(point)
        index = self._transform_controller.TransformModel.AddPoint(newpoint)

        # Ensure only the new point is selected
        self._selected_points.clear()
        self._selected_points.add(index)

        # Queue up a translate command to move the point to the new position if the LMB is still down
        registration_command = pyre.commands.stos.RegisterControlPointCommand(  # type: ignore[attr-defined]
            selected_points=self._selected_points,
            command_points={index},
            source_image=self._source_image,
            target_image=self._target_image,
            completed_func=self.check_for_cancel)
        self._commandqueue.put(registration_command)
        self.deactivate()
        return

    def check_for_cancel(self, command: ICommand):
        # Undo the addition of the translation was cancelled
        if command.status == pyre.CommandStatus.Completed and \
                command.result != pyre.CommandResult.Executed:
            self._transform_controller.SetPoints(self._original_points)
            super().cancel()
            return
        else:
            self.execute()
            return
