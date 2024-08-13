from __future__ import annotations

import abc
import dataclasses
import numpy as np
from numpy.typing import NDArray
from typing import Callable
import enum
from pyre.ui.camera import Camera

from nornir_imageregistration import PointLike


class ICommand(abc.ABC):
    """Interface to a UI command"""

    @abc.abstractmethod
    def execute(self):
        """Called when the command should execute.  The command can invoke this itself."""
        raise NotImplementedError()

    @abc.abstractmethod
    def can_execute(self) -> bool:
        """Return True if the command can execute"""
        raise NotImplementedError()

    @abc.abstractmethod
    def cancel(self):
        """Called when the command should cancel.  The command can invoke this itself."""
        raise NotImplementedError()

    @property
    @abc.abstractmethod
    def active(self) -> bool:
        """True if the command is active.  Should be set to false after execute or cancel is called"""
        raise NotImplementedError()

    @property
    @abc.abstractmethod
    def executed(self) -> bool | None:
        """True if the command has been executed, false if the command has canceled, None if the command is active"""
        raise NotImplementedError()

    @abc.abstractmethod
    def activate(self):
        """Activate the command, this should prompt it to subscribe to any required events and respond to input"""
        raise NotImplementedError()

    @abc.abstractmethod
    def add_completed_callback(self, callback: CompletionCallback):
        """Add a callback to be called when the command completes"""
        raise NotImplementedError()


# A callback function when the command is complete. The first parameter is the command that completed,
# use the executed attribute to determine if the command executed or canceled
CompletionCallback = Callable[[ICommand], None]


class SelectionEvent(enum.Enum):
    """Events that can trigger a selection"""
    Press = 1
    Release = 2
    Drag = 3


class InputType(enum.Enum):
    """Type of input"""
    Mouse = 1
    Touch = 2
    Pen = 3
    Keyboard = 4


@dataclasses.dataclass
class SelectionEventData:
    """Describes an input event that triggers a selection"""

    camera: Camera  # Describes the camera state at the time of the event
    type: InputType
    event: SelectionEvent
    world_position: NDArray[np.floating]  # The world position of the event
