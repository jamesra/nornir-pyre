import inspect
from typing import Any

import wx
import wx.lib.newevent

from pyre.interfaces import EventCallbackType, IEventManager
from pyre.ui.events.invoke_on_main_thread_event import wxInvokeOnMainThreadEvent


class wxEventManager(IEventManager[EventCallbackType]):
    """
    Implements an event manager that uses wx post to invoke events on the main wx thread
    """
    _listeners = list[EventCallbackType]
    _event_type: Any
    _event_binder: wx.PyEventBinder
    _description: str  # Description of the event manager to print in debug messages

    def __init__(self, description: str | None = None):
        self._listeners = []
        self._description = description if description is not None else self._get_invoking_class()
        # # self._event_type = wx.NewEventType()  # Create an event type for this instance of the manager
        # self._event_type, self._event_binder = wx.lib.newevent.NewEvent()
        #
        # # self._event_binder = wx.PyEventBinder(self._event_type)  # Create an event binder for this instance of the manager
        # # self._event_bind.Bind(function=self._wx_event_handler,
        # #                     id1=wx.ID_ANY, id2=wx.ID_ANY)  # Bind the event to the event handler
        # self._event_binder.Bind(self._wx_event_handler)

    @staticmethod
    def _get_invoking_class() -> str | None:
        """Get the class name of the object that invoked the method that invoked this function"""
        frame = inspect.stack()[2]
        local_vars = frame.frame.f_locals
        caller_instance = local_vars.get('self', None)
        return caller_instance.__class__.__name__ if caller_instance is not None else None

    def add(self, func: EventCallbackType):
        self._listeners.append(func)

    def remove(self, func: EventCallbackType):
        self._listeners.remove(func)

    def invoke(self, *args, **kwargs):
        print(f'wxEventManager.invoke {self._description} args={args} kwargs={kwargs}')
        if wx.IsMainThread():
            for listener in self._listeners:
                listener(*args, **kwargs)
        else:
            # If we are not on the main thread, invoke the event on the main thread
            event = wxInvokeOnMainThreadEvent(obj=self, args=args, kwargs=kwargs)
            wx.PostEvent(wx.GetApp().GetTopWindow(), event)
