import abc
from enum import Enum
from typing import Callable

import wx

from pyre.interfaces.action import Action

WindowManagerChangeCallback = Callable[[Action, str, wx.Frame], None]


class IWindowManager(abc.ABC):
    """Tracks various windows and their associated frames"""

    @abc.abstractmethod
    def add(self, key: str | Enum, frame: wx.Frame):
        """Add an image to the manager"""
        raise NotImplementedError()

    @abc.abstractmethod
    def __getitem__(self, key: str | Enum) -> wx.Frame:
        raise NotImplementedError()

    @abc.abstractmethod
    def __delitem__(self, key: str | Enum):
        raise NotImplementedError()

    @abc.abstractmethod
    def __contains__(self, key: str | Enum) -> bool:
        raise NotImplementedError()

    def exit(self):
        """Destroy all windows and exit the application"""
        raise NotImplementedError()

    def any_visible_windows(self) -> bool:
        """Return True if any windows are visible"""
        raise NotImplementedError()

    def toggle_window_visible(self, key: str | Enum):
        """Shows a window if hidden, hides a window if shown"""
        raise NotImplementedError()

    @abc.abstractmethod
    def add_change_event_listener(self, func: WindowManagerChangeCallback):
        raise NotImplementedError()

    @abc.abstractmethod
    def remove_change_event_listener(self, func: WindowManagerChangeCallback):
        raise NotImplementedError()
