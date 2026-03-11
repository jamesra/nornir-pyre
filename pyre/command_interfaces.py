"""Deprecated: command interfaces moved to pyre.interfaces. Import from pyre.interfaces instead."""

from pyre.interfaces import (
    CommandResult,
    CommandStatus,
    ICommand,
    IInstantCommand,
    StatusChangeCallback,
)

__all__ = [
    "CommandResult",
    "CommandStatus",
    "ICommand",
    "IInstantCommand",
    "StatusChangeCallback",
]
