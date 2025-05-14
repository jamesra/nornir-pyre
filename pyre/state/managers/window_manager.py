"""Handles shared image resources"""
from __future__ import annotations

from enum import Enum

import wx

from pyre.eventmanager import wxEventManager
from pyre.interfaces import IEventManager
from pyre.interfaces.managers import IWindowManager, WindowManagerChangeCallback
from pyre.interfaces.action import Action
from pyre.interfaces.viewtype import convert_to_key


# Change event for the ImageManager, passes the key and the ImagePermutationHelper associated with the key


class WindowManager(IWindowManager):
    """Tracks various windows and their associated frames"""
    _windows: dict[str, wx.Frame]
    _change_event: IEventManager[WindowManagerChangeCallback]

    def __init__(self):
        self._windows = {}
        self._change_event = wxEventManager[WindowManagerChangeCallback]()

    def add(self, key: str | Enum, frame: wx.Frame):
        key = convert_to_key(key)
        if key in self._windows:
            raise KeyError(f"Image with key {key} already exists in the manager")

        print(f'Adding window "{key}"')

        self._windows[key] = frame
        self._change_event.invoke(Action.ADD, key, frame)

    def __delitem__(self, key: str | Enum):
        key = convert_to_key(key)
        print(f"Removing window {key}")
        value = self._windows[key]
        del self._windows[key]
        self._change_event.invoke(Action.REMOVE, key, value)

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
        self._change_event.add(func)

    def remove_change_event_listener(self, func: WindowManagerChangeCallback):
        """Callbacks are invoked when a GLContext is created, or if a context already exists,
         immediately upon registration."""
        self._change_event.remove(func)
