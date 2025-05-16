from __future__ import annotations
import inspect
from typing import Any, Callable, TypeVar

from PyQt6.QtCore import QObject, QEvent, QCoreApplication, QThread, pyqtSignal, QTimer
from PyQt6.QtWidgets import QApplication

from pyre.interfaces import EventCallbackType, IEventManager


def qt_post_to_main(callback: Callable, *args, **kwargs):
    """Call a function on the main thread"""
    QTimer.singleShot(0, lambda: callback(*args, **kwargs))


class QtInvokeOnMainThreadEvent(QEvent):
    """
    Custom QEvent for invoking callbacks on the main thread
    """
    # Create a custom event type
    EVENT_TYPE = QEvent.Type(QEvent.Type.User + 1)

    def __init__(self, obj: QtEventManager, args: tuple = None, kwargs: dict = None):
        super().__init__(QtInvokeOnMainThreadEvent.EVENT_TYPE)
        self._obj = obj
        self._args = args if args is not None else tuple()
        self._kwargs = kwargs if kwargs is not None else {}

        # For debugging
        self._stack = None
        if obj._debug:
            import traceback
            self._stack = '\n'.join(traceback.format_stack())

    def invoke(self):
        """Invoke the callback for the event"""
        try:
            self._obj._invoke_on_main_thread(*self._args, **self._kwargs)
        except Exception as e:
            if self._obj._debug and self._stack:
                print(f"Exception invoking event {e} from {self._stack}")
            else:
                print(f"Exception invoking event {e}")
            raise


class QtEventManager(QObject, IEventManager[EventCallbackType]):
    """
    Implements an event manager that uses Qt events to invoke callbacks on the main Qt thread.

    This class is the Qt equivalent of wxEventManager and provides the same functionality
    using Qt's event system instead of wxPython's.
    """
    # Signal for invoking callbacks on the main thread
    invoke_signal = pyqtSignal(tuple, dict)

    # Type hints for class attributes
    _listeners: list[EventCallbackType]
    _description: str  # Description of the event manager to print in debug messages
    _debug: bool  # Whether to enable debug output

    def __init__(self, description: str | None = None):
        super().__init__()
        self._listeners = []
        self._description = description if description is not None else self._get_invoking_class()
        self._debug = False

        # Try to get debug setting from config
        try:
            from dependency_injector.wiring import Provide
            from pyre.container import IContainer
            config = Provide[IContainer.config]
            if "debug" in config:
                self._debug = bool(config["debug"])
        except Exception:
            # If we can't get the config, default to False
            pass

        # Connect the signal to the slot
        self.invoke_signal.connect(self._signal_handler)

    @staticmethod
    def _get_invoking_class() -> str | None:
        """Get the class name of the object that invoked the method that invoked this function"""
        frame = inspect.stack()[2]
        local_vars = frame.frame.f_locals
        caller_instance = local_vars.get('self', None)
        return caller_instance.__class__.__name__ if caller_instance is not None else None

    def add(self, func: EventCallbackType):
        """Add a listener to the event manager"""
        self._listeners.append(func)

    def remove(self, func: EventCallbackType):
        """Remove a listener from the event manager"""
        self._listeners.remove(func)

    def _invoke_on_main_thread(self, *args, **kwargs):
        """Invoke all listeners with the given arguments"""
        for listener in self._listeners:
            listener(*args, **kwargs)

    def _signal_handler(self, args, kwargs):
        """Handler for the invoke_signal"""
        self._invoke_on_main_thread(*args, **kwargs)

    @staticmethod
    def _is_on_main_thread() -> bool:
        """Check if the current thread is the main thread"""
        app_instance = QCoreApplication.instance()
        # If the application hasn't been initialized yet, assume we're on the main thread
        if app_instance is None:
            return True
        return QThread.currentThread() == app_instance.thread()

    def invoke(self, *args, **kwargs):
        """Invoke an event"""
        print(f'QtEventManager.invoke {self._description} args={args} kwargs={kwargs}')

        # Check if we're on the main thread
        if self._is_on_main_thread():
            # If we're on the main thread, invoke directly
            self._invoke_on_main_thread(*args, **kwargs)
        else:
            # If we're not on the main thread, post an event to the main thread
            app = QApplication.instance()
            if app:
                # First try using the signal-slot mechanism for thread-safe invocation
                try:
                    self.invoke_signal.emit(args, kwargs)
                except Exception as e:
                    if self._debug:
                        print(f"Failed to emit signal: {e}, falling back to postEvent")

                    # If signal-slot fails, fall back to posting an event
                    event = QtInvokeOnMainThreadEvent(self, args, kwargs)
                    QCoreApplication.postEvent(app, event)
            else:
                # Try to use QCoreApplication directly
                try:
                    event = QtInvokeOnMainThreadEvent(self, args, kwargs)
                    QCoreApplication.postEvent(QCoreApplication.instance(), event)
                except Exception as e:
                    print(f"Failed to post event: {e}, no QApplication instance found")
