import wx
import wx.glcanvas

wx_GL_CONTEXT_CREATED_EventType = wx.NewEventType()
wx_EVT_GL_CONTEXT_CREATED = wx.PyEventBinder(wx_GL_CONTEXT_CREATED_EventType, 1)


class wxGLContextCreatedEvent(wx.PyCommandEvent):
    """A wx window event that is sent when a new GL context is created so GL objects can be created in that context"""
    _context: wx.glcanvas.GLContext

    @property
    def context(self) -> wx.glcanvas.GLContext:
        return self._context

    def __init__(self, context: wx.glcanvas.GLContext, id: int = wx.ID_ANY):
        super().__init__(wx_GL_CONTEXT_CREATED_EventType, id)
        self._context = context
