import wx
import wx.glcanvas
from pyre.interfaces import IEventManager

wx_GL_CONTEXT_CREATED_EventType = wx.NewEventType()
wx_EVT_GL_CONTEXT_CREATED = wx.PyEventBinder(wx_GL_CONTEXT_CREATED_EventType, 1)


class wxGLContextCreatedEvent(wx.PyEvent):
    """A wx window event that is sent when a new GL context is created so GL objects can be created in that context"""
    _context: wx.glcanvas.GLContext

    @property
    def context(self) -> wx.glcanvas.GLContext:
        return self._context

    def __init__(self, context: wx.glcanvas.GLContext, id: int = wx.ID_ANY):
        super().__init__(eventType=wx_GL_CONTEXT_CREATED_EventType, id=id)
        self._context = context


# An event that invokes a callback on the main thread
wx_INVOKE_ON_MAIN_THREAD_EventType = wx.NewEventType()
wx_EVT_INVOKE_ON_MAIN_THREAD = wx.PyEventBinder(wx_INVOKE_ON_MAIN_THREAD_EventType)


class wxInvokeOnMainThreadEvent(wx.PyEvent):
    _args: tuple | None
    _kwargs: dict | None
    _obj: IEventManager

    @property
    def args(self) -> tuple | None:
        return self._args

    @property
    def kwargs(self) -> dict | None:
        return self._kwargs

    @property
    def obj(self) -> IEventManager | None:
        return self._obj

    def __init__(self, obj: IEventManager,
                 args: tuple | None = None,
                 kwargs: dict | None = None):
        super().__init__(id=wx.ID_ANY, eventType=wx_INVOKE_ON_MAIN_THREAD_EventType)
        self._args = args
        self._kwargs = kwargs
        self._obj = obj

    def invoke(self):
        """Invoke the callback for the event"""
        self._obj.invoke(*self._args, **self._kwargs)
