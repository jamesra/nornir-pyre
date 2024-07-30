from __future__ import annotations

import abc

import wx

from pyre.commands.interfaces import CompletionCallback, ICommand


class CommandBase(ICommand):
    """
    Helper implementation for commands
    """

    _command_completed_callbacks: list[CompletionCallback]
    _parent: wx.Window
    _active: bool = False

    @property
    def active(self) -> bool:
        return self._active

    @property
    def parent(self):
        """Parent window the command is bound to and subscribes to events from"""
        return self._parent

    def end_command(self):
        """function called when the command is finished"""
        for callback in self._command_completed_callbacks:
            wx.CallAfter(callback)

        self.unsubscribe_to_parent()

    @abc.abstractmethod
    def subscribe_to_parent(self):
        raise NotImplemented(
            "All commands should implement subscribe_to_parent which binds to events on the parent window")

    @abc.abstractmethod
    def unsubscribe_to_parent(self):
        raise NotImplemented(
            "All commands should implement unsubscribe_to_parent which executes when the command is completed")

    def __init__(self,
                 parent: wx.Window,
                 completed_func: CompletionCallback | None = None):
        """
        :param window parent: Window to subscribe to for events
        :param func completed_func: Function to call when command has completed
        """
        self._parent = parent
        self._command_completed_callbacks = list()
        if completed_func is not None:
            self._command_completed_callbacks.append(completed_func)

        self._bind_mouse_events()

    def activate(self):
        self.subscribe_to_parent()
        _active = True

    def add_completed_callback(self, callback: CompletionCallback):
        self._command_completed_callbacks.append(callback)

    def _bind_mouse_events(self):
        self._parent.Bind(wx.EVT_MOUSEWHEEL, self.on_mouse_scroll)
        self._parent.Bind(wx.EVT_LEFT_DOWN, self.on_mouse_press)
        self._parent.Bind(wx.EVT_MIDDLE_DOWN, self.on_mouse_press)
        self._parent.Bind(wx.EVT_RIGHT_DOWN, self.on_mouse_press)
        self._parent.Bind(wx.EVT_MOTION, self.on_mouse_motion)
        self._parent.Bind(wx.EVT_LEFT_UP, self.on_mouse_release)

    def _unbind_mouse_events(self):
        self._parent.Unbind(wx.EVT_LEFT_DOWN, self.on_mouse_press)
        self._parent.Unbind(wx.EVT_MIDDLE_DOWN, self.on_mouse_press)
        self._parent.Unbind(wx.EVT_RIGHT_DOWN, self.on_mouse_press)
        self._parent.Unbind(wx.EVT_MOTION, self.on_mouse_motion)
        self._parent.Unbind(wx.EVT_LEFT_UP, self.on_mouse_release)
        self._parent.Unbind(wx.EVT_MOUSEWHEEL, self.on_mouse_scroll)

    def _bind_key_events(self):
        self._parent.Bind(wx.EVT_KEY_DOWN, self.on_key_down)
        self._parent.Bind(wx.EVT_KEY_UP, self.on_key_up)

    def _unbind_key_events(self):
        self._parent.Unbind(wx.EVT_KEY_DOWN, self.on_key_down)
        self._parent.Unbind(wx.EVT_KEY_UP, self.on_key_up)

    @abc.abstractmethod
    def on_mouse_press(self, event: wx.MouseEvent):
        raise NotImplementedError()

    @abc.abstractmethod
    def on_mouse_motion(self, event: wx.MouseEvent):
        raise NotImplementedError()

    @abc.abstractmethod
    def on_mouse_release(self, event: wx.MouseEvent):
        raise NotImplementedError()

    @abc.abstractmethod
    def on_mouse_scroll(self, event: wx.MouseEvent):
        raise NotImplementedError()

    @abc.abstractmethod
    def on_key_down(self, event: wx.KeyEvent):
        raise NotImplementedError()

    @abc.abstractmethod
    def on_key_up(self, event: wx.KeyEvent):
        raise NotImplementedError()
