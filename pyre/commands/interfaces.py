from __future__ import annotations

import abc
from typing import Callable


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
