"""Handles shared image resources"""
import abc
import wx
import numpy as np
from typing import Callable
from numpy.typing import NDArray
import nornir_imageregistration
from .viewtype import ViewType, convert_to_key
from enum import Enum
from .events import Action

# Change event for the ImageManager, passes the key and the ImagePermutationHelper associated with the key
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


class WindowManager(IWindowManager):
    _windows: dict[str, wx.Frame]
    _change_event_listeners: list[WindowManagerChangeCallback]

    def __init__(self):
        self._windows = {}

    def add(self, key: str | Enum, frame: wx.Frame):
        key = convert_to_key(key)
        if key in self._windows:
            raise KeyError(f"Image with key {key} already exists in the manager")

        self._windows[key] = frame

    def __delitem__(self, key: str | Enum):
        key = convert_to_key(key)
        del self._windows[key]

    def __contains__(self, key: str | Enum) -> bool:
        key = convert_to_key(key)
        return key in self._windows

    def __getitem__(self, name: str | Enum) -> wx.Frame:
        """Get the GL ImageViewModel for the image"""
        key = convert_to_key(name)
        return self._windows[key]

    def exit(self):
        """Destroy all windows and exit the application"""
        for w in self._windows.values():
            w.Destroy()

    @property
    def any_visible_windows(self) -> bool:
        """Return True if any windows are visible"""
        for w in self._windows.values():
            if w.IsShown():
                return True

        return False

    def toggle_window_visible(self, key: str | Enum):
        """Shows a window if hidden, hides a window if shown.
        If all windows are hidden, exit the application."""
        key = convert_to_key(key)
        if key in self._windows:
            w = self._windows[key]
            if w.IsShown():
                w.Hide()
            else:
                w.Show()

        if not self.any_visible_windows:
            self.exit()

    def add_change_event_listener(self, func: WindowManagerChangeCallback):
        """Callbacks are invoked when a GLContext is created, or if a context already exists,
         immediately upon registration."""
        self._change_event_listeners.append(func)

    def remove_change_event_listener(self, func: WindowManagerChangeCallback):
        """Callbacks are invoked when a GLContext is created, or if a context already exists,
         immediately upon registration."""
        self._change_event_listeners.remove(func)
