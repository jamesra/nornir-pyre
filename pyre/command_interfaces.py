from __future__ import annotations

import abc
import enum
from typing import Callable


class CommandResult(enum.IntEnum):
    """Outcome of a command"""
    Unknown = -1
    Canceled = 0  # The command was cancelled
    Executed = 1  # The command completed successfully


class CommandStatus(enum.IntEnum):
    """Status of a command"""
    NotStarted = -1  # The command has not been started
    Active = 0  # The command is in progress and can still recieve user input
    Inactive = 1  # The command is no longer recieving input, but has not completed
    Completed = 2  # The command has completed


class IInstantCommand(abc.ABC):
    """Interface to a UI command that executes immediately without user input"""

    @abc.abstractmethod
    def execute(self):
        """Called when the command should execute.  The command can invoke this itself."""
        raise NotImplementedError()

    @abc.abstractmethod
    def cancel(self):
        """Called when the command should cancel.  The command can invoke this itself."""
        raise NotImplementedError()

    @property
    @abc.abstractmethod
    def result(self) -> CommandResult:
        """Outcome of the command"""
        raise NotImplementedError()

    @property
    @abc.abstractmethod
    def status(self) -> CommandStatus:
        """Outcome of the command"""
        raise NotImplementedError()

    @abc.abstractmethod
    def add_completed_callback(self, callback: StatusChangeCallback):
        """Add a callback to be called when the command completes"""
        raise NotImplementedError()

    @abc.abstractmethod
    def activate(self):
        """Activate the command, this should prompt it to subscribe to any required events and respond to input"""
        raise NotImplementedError()

    @abc.abstractmethod
    def deactivate(self):
        """Deactivate the command, this should prompt it to unsubscribe from any events.  It may still
        remain in progress if it is waiting for a child command to complete"""
        raise NotImplementedError()


class ICommand(IInstantCommand):
    """Interface to a UI command the requires interaction with the user"""

    @abc.abstractmethod
    def can_execute(self) -> bool:
        """Return True if the command can execute in its current state"""
        raise NotImplementedError()


# A callback function when the command is complete. The first parameter is the command that completed,
# use the executed attribute to determine if the command executed or canceled
StatusChangeCallback = Callable[[ICommand], None]
