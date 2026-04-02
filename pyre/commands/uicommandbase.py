from __future__ import annotations

import abc
import types
from typing import Any

from PyQt6.QtCore import QObject, QTimer, QEvent, Qt
from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QMouseEvent, QKeyEvent, QResizeEvent

import pyre
from pyre.interfaces import IInstantCommand, StatusChangeCallback, ICommand


class CommandBase(IInstantCommand):
    """Shared implementation for all commands"""
    _command_completed_callbacks: list[StatusChangeCallback]
    _result: pyre.CommandResult
    _status: pyre.CommandStatus

    @property
    def result(self) -> pyre.CommandResult:
        """Result of the command once it completes."""
        return self._result

    @property
    def executed(self) -> bool:
        """Whether the command completed with an executed result."""
        return self._status == pyre.CommandResult.Executed

    @property
    def cancelled(self) -> bool:
        """Whether the command completed with a canceled result."""
        return self._status == pyre.CommandResult.Canceled

    @property
    def status(self) -> pyre.CommandStatus:
        """Current command lifecycle state."""
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
            self._call_on_status_change()

    @abc.abstractmethod
    def _call_on_status_change(self):
        """function called when the command is finished with the UI.  It
        may still wait to commit to the action if it is part of a sequence of commands and it is
        waiting for a callback from a command it spawned.  In this case it may still be active"""
        raise NotImplementedError()

    def __init__(self,
                 completed_func: StatusChangeCallback | None = None):
        """
        :param window parent: Window to subscribe to for events
        :param func completed_func: Function to call when command has completed
        """
        self._status = pyre.CommandStatus.NotStarted
        self._result = pyre.CommandResult.Unknown
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

    def activate(self):
        self.status = pyre.CommandStatus.Active
        self.on_activate()

    def on_activate(self):
        """Override this in derived classes to execute code when the command is activated"""
        pass

    def add_completed_callback(self, callback: StatusChangeCallback):
        self._command_completed_callbacks.append(callback)

    def _notify_completed_callbacks(self):
        for callback in self._command_completed_callbacks:
            QTimer.singleShot(0, lambda cb=callback: cb(self))


class InstantCommandBase(CommandBase, IInstantCommand, abc.ABC):
    """
    Helper implementation for commands that execute instantly
    """

    def __init__(self,
                 completed_func: StatusChangeCallback | None = None):
        super().__init__(completed_func)

    def _call_on_status_change(self):
        """function called when the command is finished with the UI.  It
        may still wait to commit to the action if it is part of a sequence of commands and it is
        waiting for a callback from a command it spawned.  In this case it may still be active"""
        self._notify_completed_callbacks()


class UICommandBase(ICommand, CommandBase, abc.ABC):
    """
    Helper implementation for commands that interact with the UI
    """

    _parent: QWidget
    _width: int
    _height: int
    _saved_mouse_tracking: bool | None

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

    def _call_on_status_change(self):
        """function called when the command is finished with the UI.  It
        may still wait to commit to the action if it is part of a sequence of commands and it is
        waiting for a callback from a command it spawned.  In this case it may still be active"""
        self._notify_completed_callbacks()

        if self._status == pyre.CommandStatus.Completed or self._status == pyre.CommandStatus.Inactive:
            self.unsubscribe_to_parent()

    @abc.abstractmethod
    def subscribe_to_parent(self):
        raise NotImplementedError()

    @abc.abstractmethod
    def unsubscribe_to_parent(self):
        raise NotImplementedError()

    def __init__(self,
                 parent: QWidget,
                 completed_func: StatusChangeCallback | None = None):
        """
        :param window parent: Window to subscribe to for events
        :param func completed_func: Function to call when command has completed
        """
        super().__init__(completed_func=completed_func)
        self._parent = parent
        self._width, self._height = parent.size().width(), parent.size().height()
        self._saved_resizeEvent = None
        self._saved_wheelEvent = None
        self._saved_mousePressEvent = None
        self._saved_mouseMoveEvent = None
        self._saved_mouseReleaseEvent = None
        self._saved_keyPressEvent = None
        self._saved_keyReleaseEvent = None
        self._saved_mouse_tracking = None

    def on_resize(self, event: QResizeEvent):
        """Resize our window the command is active within"""
        self._width, self._height = event.size().width(), event.size().height()

    def activate(self):
        super().activate()
        self.subscribe_to_parent()

    def deactivate(self):
        self.unsubscribe_to_parent()
        super().deactivate()

    def _restore_class_event(self, attr: str) -> None:
        """Bind the widget class's default slot to this parent (assigning the bare class method breaks PyQt)."""
        unbound = getattr(self._parent.__class__, attr)
        setattr(self._parent, attr, types.MethodType(unbound, self._parent))

    def _ensure_bound_instance_method(self, attr: str):
        """If a previous bug left an unbound class method on the widget, bind it before we save the chain."""
        cur = getattr(self._parent, attr)
        if cur is None:
            return None
        if getattr(cur, "__self__", None) is None:
            unbound = getattr(self._parent.__class__, attr)
            bound = types.MethodType(unbound, self._parent)
            setattr(self._parent, attr, bound)
            return bound
        return cur

    def _bind_resize_event(self):
        self._saved_resizeEvent = self._ensure_bound_instance_method("resizeEvent")
        self._parent.resizeEvent = self._handle_resize_event  # type: ignore[method-assign]

    def _unbind_resize_event(self):
        if self._saved_resizeEvent is not None:
            self._parent.resizeEvent = self._saved_resizeEvent  # type: ignore[method-assign]
            self._saved_resizeEvent = None
        else:
            self._restore_class_event("resizeEvent")

    def _handle_resize_event(self, event):
        if self._saved_resizeEvent is not None:
            self._saved_resizeEvent(event)
        self.on_resize(event)

    def _bind_mouse_events(self):
        # Ensure hover/move events are delivered even with no button pressed.
        # Some command flows rely on this for cursor updates and hit-testing.
        self._saved_mouse_tracking = self._parent.hasMouseTracking()
        self._parent.setMouseTracking(True)
        self._saved_wheelEvent = self._ensure_bound_instance_method("wheelEvent")
        self._saved_mousePressEvent = self._ensure_bound_instance_method("mousePressEvent")
        self._saved_mouseMoveEvent = self._ensure_bound_instance_method("mouseMoveEvent")
        self._saved_mouseReleaseEvent = self._ensure_bound_instance_method("mouseReleaseEvent")
        self._parent.wheelEvent = self._handle_wheel_event  # type: ignore[method-assign]
        self._parent.mousePressEvent = self._handle_mouse_press_event  # type: ignore[method-assign]
        self._parent.mouseMoveEvent = self._handle_mouse_move_event  # type: ignore[method-assign]
        self._parent.mouseReleaseEvent = self._handle_mouse_release_event  # type: ignore[method-assign]

    def _unbind_mouse_events(self):
        if self._saved_wheelEvent is not None:
            self._parent.wheelEvent = self._saved_wheelEvent  # type: ignore[method-assign]
            self._saved_wheelEvent = None
        else:
            self._restore_class_event("wheelEvent")
        if self._saved_mousePressEvent is not None:
            self._parent.mousePressEvent = self._saved_mousePressEvent  # type: ignore[method-assign]
            self._saved_mousePressEvent = None
        else:
            self._restore_class_event("mousePressEvent")
        if self._saved_mouseMoveEvent is not None:
            self._parent.mouseMoveEvent = self._saved_mouseMoveEvent  # type: ignore[method-assign]
            self._saved_mouseMoveEvent = None
        else:
            self._restore_class_event("mouseMoveEvent")
        if self._saved_mouseReleaseEvent is not None:
            self._parent.mouseReleaseEvent = self._saved_mouseReleaseEvent  # type: ignore[method-assign]
            self._saved_mouseReleaseEvent = None
        else:
            self._restore_class_event("mouseReleaseEvent")

        if self._saved_mouse_tracking is not None:
            self._parent.setMouseTracking(self._saved_mouse_tracking)
            self._saved_mouse_tracking = None

    def _handle_wheel_event(self, event):
        if self._saved_wheelEvent is not None:
            self._saved_wheelEvent(event)
        self.on_mouse_scroll(event)

    def _handle_mouse_press_event(self, event):
        if self._saved_mousePressEvent is not None:
            self._saved_mousePressEvent(event)
        self.on_mouse_press(event)

    def _handle_mouse_move_event(self, event):
        if self._saved_mouseMoveEvent is not None:
            self._saved_mouseMoveEvent(event)
        self.on_mouse_motion(event)

    def _handle_mouse_release_event(self, event):
        if self._saved_mouseReleaseEvent is not None:
            self._saved_mouseReleaseEvent(event)
        self.on_mouse_release(event)

    def _bind_key_events(self):
        self._saved_keyPressEvent = self._ensure_bound_instance_method("keyPressEvent")
        self._saved_keyReleaseEvent = self._ensure_bound_instance_method("keyReleaseEvent")
        self._parent.keyPressEvent = self._handle_key_press_event  # type: ignore[method-assign]
        self._parent.keyReleaseEvent = self._handle_key_release_event  # type: ignore[method-assign]

    def _unbind_key_events(self):
        if self._saved_keyPressEvent is not None:
            self._parent.keyPressEvent = self._saved_keyPressEvent  # type: ignore[method-assign]
            self._saved_keyPressEvent = None
        else:
            self._restore_class_event("keyPressEvent")
        if self._saved_keyReleaseEvent is not None:
            self._parent.keyReleaseEvent = self._saved_keyReleaseEvent  # type: ignore[method-assign]
            self._saved_keyReleaseEvent = None
        else:
            self._restore_class_event("keyReleaseEvent")

    def _handle_key_press_event(self, event):
        if self._saved_keyPressEvent is not None:
            self._saved_keyPressEvent(event)
        self.on_key_down(event)

    def _handle_key_release_event(self, event):
        if self._saved_keyReleaseEvent is not None:
            self._saved_keyReleaseEvent(event)
        self.on_key_up(event)

    @abc.abstractmethod
    def on_mouse_press(self, event: QMouseEvent):
        pass

    @abc.abstractmethod
    def on_mouse_motion(self, event: QMouseEvent):
        pass

    @abc.abstractmethod
    def on_mouse_release(self, event: QMouseEvent):
        pass

    @abc.abstractmethod
    def on_mouse_scroll(self, event: QMouseEvent):
        pass

    @abc.abstractmethod
    def on_key_down(self, event: QKeyEvent):
        pass

    @abc.abstractmethod
    def on_key_up(self, event: QKeyEvent):
        pass
