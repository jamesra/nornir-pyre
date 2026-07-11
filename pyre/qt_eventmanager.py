from __future__ import annotations

import inspect
from typing import Any, Callable, TypeVar

from dependency_injector.wiring import Provide
from PyQt6.QtCore import QObject, QEvent, QCoreApplication, QThread, pyqtSignal, QTimer, Qt
from PyQt6.QtWidgets import QApplication

from pyre.interfaces import EventCallbackType, IEventManager


class _MainThreadDispatcher(QObject):
    """Queues callables onto the Qt GUI thread from worker threads."""

    request = pyqtSignal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.request.connect(self._dispatch, Qt.ConnectionType.QueuedConnection)

    def _dispatch(self, fn: Callable[[], None]) -> None:
        fn()


_main_thread_dispatcher: _MainThreadDispatcher | None = None


def _get_main_thread_dispatcher(app: QApplication) -> _MainThreadDispatcher:
    global _main_thread_dispatcher
    if _main_thread_dispatcher is None:
        _main_thread_dispatcher = _MainThreadDispatcher(app)
    return _main_thread_dispatcher


def init_main_thread_dispatcher() -> None:
    """Create the GUI-thread dispatcher; call once from the main thread after QApplication exists."""
    app = QApplication.instance()
    if app is not None:
        _get_main_thread_dispatcher(app)


def qt_post_to_main(callback: Callable, *args, activate_context: Callable[[], None] | None = None, **kwargs) -> None:
    """Call a function on the main thread, optionally activating OpenGL context first.
    
    :param callback: The function to call on the main thread
    :param *args: Positional arguments to pass to the callback
    :param activate_context: Optional function to call before the callback to activate OpenGL context (keyword-only)
    :param **kwargs: Keyword arguments to pass to the callback
    """
    def wrapped():
        if activate_context is not None:
            activate_context()
        callback(*args, **kwargs)

    app = QApplication.instance()
    on_main = app is None or QThread.currentThread() == app.thread()
    if app is not None and not on_main:
        _get_main_thread_dispatcher(app).request.emit(wrapped)
    else:
        QTimer.singleShot(0, wrapped)


class QtInvokeOnMainThreadEvent(QEvent):
    """
    Custom QEvent for invoking callbacks on the main thread
    """
    # Create a custom event type
    EVENT_TYPE = QEvent.Type(QEvent.Type.User + 1)

    def __init__(self, obj: QtEventManager, args: tuple | None = None, kwargs: dict | None = None):
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
    _description: str | None  # Description of the event manager to print in debug messages
    _debug: bool  # Whether to enable debug output

    def __init__(self, description: str | None = None):
        super().__init__()
        self._listeners = []
        self._description = description if description is not None else self._get_invoking_class()
        self._debug = False

        # Try to get debug setting from config (deferred import to avoid circular import with pyre.container)
        try:
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
