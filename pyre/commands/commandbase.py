from __future__ import annotations

import abc

import wx

import pyre
from pyre.command_interfaces import StatusChangeCallback, ICommand


class CommandBase(ICommand):
    """
    Helper implementation for commands
    """

    _command_completed_callbacks: list[StatusChangeCallback]
    _parent: wx.Window
    _result: pyre.CommandResult
    _status: pyre.CommandStatus

    @property
    def result(self) -> pyre.CommandResult:
        """True if the command has been executed"""
        return self._result

    @property
    def executed(self) -> bool:
        """True if the command has been executed"""
        return self._status == pyre.CommandResult.Executed

    @property
    def cancelled(self) -> bool:
        """True if the command has been executed"""
        return self._status == pyre.CommandResult.Canceled

    @property
    def status(self) -> pyre.CommandStatus:
        """True if the command has been executed"""
        return self._status

    @status.setter
    def status(self, value: pyre.CommandStatus):

        if self._status == pyre.CommandStatus.Completed:
            raise ValueError('Cannot set status on a command that is already completed')

        if value == pyre.CommandStatus.NotStarted:
            raise ValueError('Cannot set status to NotStarted, that is the initial state')
        elif value == pyre.CommandStatus.Active and self._status != pyre.CommandStatus.NotStarted:
            raise ValueError('Cannot set status to Active, command is already started')
        elif value == pyre.CommandStatus.Inactive and not (
                self._status == pyre.CommandStatus.Active or self._status == pyre.CommandStatus.NotStarted):
            raise ValueError('Cannot set status to Inactive, command is already started')
        elif value == pyre.CommandStatus.Completed and not (
                self._status == pyre.CommandStatus.Active or self._status == pyre.CommandStatus.Inactive):
            raise ValueError('Cannot set status to Completed, command has not started')

        self._status = value

        # We don't notify when the command executes
        if self._status != pyre.CommandStatus.Active:
            self.call_on_status_change()

    @property
    def width(self) -> int:
        """Width of the window command is active in, in pixels"""
        return self._width

    @property
    def height(self) -> int:
        """Height of the window command is active in, in pixels"""
        return self._height

    @property
    def parent(self):
        """Parent window the command is bound to and subscribes to events from"""
        return self._parent

    def call_on_status_change(self):
        """function called when the command is finished with the UI.  It
        may still wait to commit to the action if it is part of a sequence of commands and it is
        waiting for a callback from a command it spawned.  In this case it may still be active"""
        for callback in self._command_completed_callbacks:
            wx.CallAfter(callback, self)

        if self._status == pyre.CommandStatus.Completed or self._status == pyre.CommandStatus.Inactive:
            self.unsubscribe_to_parent()

    @abc.abstractmethod
    def subscribe_to_parent(self):
        raise NotImplementedError()

    @abc.abstractmethod
    def unsubscribe_to_parent(self):
        raise NotImplementedError()

    def __init__(self,
                 parent: wx.Window,
                 completed_func: StatusChangeCallback | None = None):
        """
        :param window parent: Window to subscribe to for events
        :param func completed_func: Function to call when command has completed
        """
        self._status = pyre.CommandStatus.NotStarted
        self._result = pyre.CommandResult.Unknown
        self._parent = parent
        self._width, self._height = parent.GetSize()
        self._command_completed_callbacks = list()
        if completed_func is not None:
            self._command_completed_callbacks.append(completed_func)

    def execute(self):
        self.status = pyre.CommandStatus.Completed
        self._result = pyre.CommandResult.Executed
        return

    def cancel(self):
        self._result = pyre.CommandResult.Canceled
        self.status = pyre.CommandStatus.Completed
        return

    def deactivate(self):
        """Deactivate the command by stopping listening to events from the parent window.  Do
        not commit to execution or cancellation at this time.  This should be used when the command
        is waiting for a callback from a child command it spawned to learn if it should execute or cancel"""
        self.status = pyre.CommandStatus.Inactive
        return

    def on_deactivate(self):
        """Override this in derived classes to execute code when the command is deactivated"""
        pass

    def on_resize(self, event: wx.SizeEvent):
        """Resize our window the command is active within"""
        self._width, self._height = event.GetSize()

    def activate(self):
        self.status = pyre.CommandStatus.Active
        self.subscribe_to_parent()
        self.on_activate()

    def on_activate(self):
        """Override this in derived classes to execute code when the command is activated"""
        pass

    def add_completed_callback(self, callback: StatusChangeCallback):
        self._command_completed_callbacks.append(callback)

    def _bind_resize_event(self):
        self._parent.Bind(wx.EVT_SIZE, handler=self.on_resize)

    def _unbind_resize_event(self):
        self._parent.Unbind(wx.EVT_SIZE, handler=self.on_resize)

    def _bind_mouse_events(self):
        self._parent.Bind(wx.EVT_MOUSEWHEEL, handler=self.on_mouse_scroll)
        self._parent.Bind(wx.EVT_LEFT_DOWN, handler=self.on_mouse_press)
        self._parent.Bind(wx.EVT_MIDDLE_DOWN, handler=self.on_mouse_press)
        self._parent.Bind(wx.EVT_RIGHT_DOWN, handler=self.on_mouse_press)
        self._parent.Bind(wx.EVT_MOTION, handler=self.on_mouse_motion)
        self._parent.Bind(wx.EVT_LEFT_UP, handler=self.on_mouse_release)

    def _unbind_mouse_events(self):
        self._parent.Unbind(wx.EVT_MOUSEWHEEL, handler=self.on_mouse_scroll)
        self._parent.Unbind(wx.EVT_LEFT_DOWN, handler=self.on_mouse_press)
        self._parent.Unbind(wx.EVT_MIDDLE_DOWN, handler=self.on_mouse_press)
        self._parent.Unbind(wx.EVT_RIGHT_DOWN, handler=self.on_mouse_press)
        self._parent.Unbind(wx.EVT_MOTION, handler=self.on_mouse_motion)
        self._parent.Unbind(wx.EVT_LEFT_UP, handler=self.on_mouse_release)

    def _bind_key_events(self):
        self._parent.Bind(wx.EVT_KEY_DOWN, handler=self.on_key_down)
        self._parent.Bind(wx.EVT_KEY_UP, handler=self.on_key_up)

    def _unbind_key_events(self):
        self._parent.Unbind(wx.EVT_KEY_DOWN, handler=self.on_key_down)
        self._parent.Unbind(wx.EVT_KEY_UP, handler=self.on_key_up)

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
