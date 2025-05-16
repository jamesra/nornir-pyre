from __future__ import annotations

from dependency_injector.wiring import inject, Provide
from dependency_injector.providers import Configuration
import numpy as np
from numpy.typing import NDArray
import wx

import nornir_imageregistration
import pyre
from pyre.observable import ObservableSet, ObservedAction
from pyre import Space
from pyre.command_interfaces import StatusChangeCallback, ICommand
from pyre.commands import InstantCommandBase
from pyre.interfaces.managers import ICommandQueue, IMousePositionHistoryManager
from pyre.container import IContainer
from pyre.selection_event_data import InputEvent, InputModifiers, SelectionEventData, InputSource, PointPair


class CreateRegisterControlPointCommand(InstantCommandBase):
    """This command deletes a selection of control points"""

    _space: Space
    _new_point_position: PointPair
    _selected_points: ObservableSet[int]  # The indices of the selected points

    _mouse_position_history: IMousePositionHistoryManager = Provide[IContainer.mouse_position_history]
    _original_points: NDArray[np.floating]
    _left_mouse_down: bool = False
    _transform_controller: pyre.viewmodels.TransformController
    _commandqueue: ICommandQueue

    _source_image: str
    _target_image: str

    @inject
    def __init__(self,
                 commandqueue: ICommandQueue,
                 selected_points: ObservableSet[int],  # The indices of the selected points
                 source_image: str,
                 target_image: str,
                 completed_func: StatusChangeCallback = None,
                 transform_controller: pyre.viewmodels.TransformController = Provide[IContainer.transform_controller],
                 config: Configuration = Provide[IContainer.config],
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
        wx.CallAfter(self.queue_registration_command)

    def __str__(self):
        return "CreateControlPointCommand"

    def can_execute(self) -> bool:
        return True

    def cancel(self):
        super().cancel()
        return

    def queue_registration_command(self):

        point = self._new_point_position
        # point = self._new_point_position.source if self.space == Space.Source else self._new_point_position.target
        newpoint = np.array([point.target[0], point.target[1], point.source[0], point.source[1]], dtype=np.float32)
        index = self._transform_controller.TransformModel.AddPoint(newpoint)

        # Ensure only the new point is selected
        self._selected_points.clear()
        self._selected_points.add(index)

        # Queue up a translate command to move the point to the new position if the LMB is still down
        registration_command = pyre.commands.stos.RegisterControlPointCommand(
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
