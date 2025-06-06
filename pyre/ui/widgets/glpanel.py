#!/usr/bin/python

# import OpenGL as gl

from typing import Callable

from dependency_injector.wiring import inject, Provide

import OpenGL.GL as gl

from pyre.interfaces.managers.gl_context_manager import IGLContextManager
from pyre.container import IContainer

from nornir_imageregistration import in_debug_mode

try:
    import wx
    import wx.glcanvas

except:
    print("Ignoring wx import failure, assumed documentation use, otherwise please install wxPython")


def cb_dbg_msg(source, msg_type, msg_id, severity, length, raw, user):
    msg = raw[0:length]
    print(f'debug: {source}, {msg_type}, {msg_id}, {severity}, {msg}')


# DEBUG_CALLBACK_TYPE = gl.GLDEBUGPROC(None, c_uint, c_uint, c_uint, c_uint, c_size_t, POINTER(c_char), c_void_p)

# Create a ctypes callback instance
debug_callback_func = gl.GLDEBUGPROC(cb_dbg_msg)


class GLPanel(wx.glcanvas.GLCanvas):
    """A wxPython panel that contains an OpenGL canvas. and a BoxSizer"""

    _glinitialized: bool = False
    # canvas: wx.glcanvas.GLCanvas
    sizer = wx.BoxSizer
    _draw_method: Callable[[], None]  # Method we call to render scene onto our canvas

    SharedGLContext = None  # type: wx.glcanvas.GLContext
    _glcontextmanager: IGLContextManager = Provide[IContainer.glcontext_manager]

    @inject
    def __init__(self,
                 parent: wx.Window,
                 draw_method: Callable[[], None],
                 window_id: int = wx.ID_ANY,
                 pos: wx.Point = wx.DefaultPosition,
                 size: wx.Size = wx.DefaultSize,
                 style=0,
                 **kwargs):
        self._draw_method = draw_method
        # Forcing a no full repaint to stop flickering
        style = style | wx.NO_FULL_REPAINT_ON_RESIZE | wx.WANTS_CHARS
        # call super function
        disp_attrs = wx.glcanvas.GLAttributes()
        disp_attrs.PlatformDefaults().DoubleBuffer().RGBA().Depth(16).EndList()
        super(GLPanel, self).__init__(parent=parent, dispAttrs=disp_attrs,
                                      id=window_id, pos=pos, size=size,
                                      style=style, **kwargs)

        # init gl canvas data
        # Create context
        # self.canvas = wx.glcanvas.GLCanvas(self, disp_attrs, -1)

        context_attrs = wx.glcanvas.GLContextAttrs()

        if in_debug_mode():
            context_attrs.PlatformDefaults().CoreProfile().OGLVersion(4, 5).ForwardCompatible().DebugCtx().EndList()

        context = wx.glcanvas.GLContext(self, GLPanel.SharedGLContext, context_attrs)
        add_listener = False
        if GLPanel.SharedGLContext is None:
            # Install our debug message callback
            GLPanel.SharedGLContext = context
            add_listener = True

        self.context = context
        self.SetCurrent(self.context)

        if add_listener:
            gl.glDebugMessageCallback(debug_callback_func, None)

            if in_debug_mode():
                gl.glEnable(gl.GL_DEBUG_OUTPUT)

        #    GLPanel.pygletcontext = gl.Context(gl.current_context)

        # GLPanel.wxcontext = self.canvas.GetContext()
        # else:
        # self.canvas = wx.glcanvas.GLCanvasWithContext(self, shared=GLPanel.wxcontext, attribList=attribList)

        # Create the canvas

        # self.sizer = wx.BoxSizer(wx.VERTICAL)
        #
        # self.sizer.Add(self.canvas, 1, wx.EXPAND)
        # self.SetSizer(self.sizer)
        # self.sizer.Fit(self)
        # self.Layout()

        # bind events
        self.Bind(wx.EVT_ERASE_BACKGROUND, self.processEraseBackgroundEvent)
        self.Bind(wx.EVT_SIZE, self.processSizeEvent)
        self.Bind(wx.EVT_SIZING, self.processSizeEvent)
        self.Bind(wx.EVT_PAINT, self.processPaintEvent)

        # self.Bind(wx.EVT_SIZE, self.processSizeEvent)

        # Send an event that a context was created.
        wx.CallAfter(self.OnInitGL)
        # self.Bind(wx_EVT_GL_CONTEXT_CREATED, self.OnInitGL)

        # context_created_event = wxGLContextCreatedEvent(context=context)
        # wx.PostEvent(self, context_created_event)

    # ==========================================================================
    # Canvas Proxy Methods
    # ==========================================================================
    def GetGLExtents(self):
        """Get the extents of the OpenGL canvas."""
        return self.GetClientSize()

    # def SwapBuffers(self):
    #    """Swap the OpenGL buffers."""
    #    self.canvas.SwapBuffers()

    # ==========================================================================
    # wxPython Window Handlers
    # ==========================================================================
    def processEraseBackgroundEvent(self, event):
        """Process the erase background event."""
        pass  # Do nothing, to avoid flashing on MSWin

    def processSizeEvent(self, event):
        """Process the resize event."""
        # Make sure the frame is shown before calling SetCurrent.
        self.Show()
        self.SetCurrent(self.context)
        size = self.GetGLExtents()
        self.width, self.height = size.width, size.height
        self.OnReshape(size.width, size.height)
        self.Refresh(False)

        event.Skip()

    def processPaintEvent(self, event):
        """Process the drawing event."""
        # self.canvas.SetCurrent(GLPanel.SharedGLContext)
        self.OnDraw()
        event.Skip()

    def Destroy(self):
        # call the super method
        super(GLPanel, self).Destroy()

    # def OnContextCreated(self, event):
    #     """Called when our custom wx_EVT_GL_CONTEXT_CREATED event is received"""
    #     self.OnInitGL()
    #     event.Skip()

    # ==========================================================================
    # GLFrame OpenGL Event Handlers
    # ==========================================================================
    def OnInitGL(self):
        """
        Initialize OpenGL for use in the window.  This is invoked by the
        wx.EVT_GL_CONTEXT_CREATED event.  This call notifies the GLContextManager
        after it has completed its own initialization.
        """
        if self._glinitialized:
            return

        #         GLPanel.pygletcontext = gl.Context(gl.current_context)
        #         GLPanel.pygletcontext.canvas = self
        #
        #         GLPanel.pygletcontext.set_current()

        # Set the current context as our context.  This is expected by create_objects
        self.SetCurrent(self.context)

        # Notify the context manager that a new context has been created
        self._glcontextmanager.add_context(self.context)

        # allow inheritors the chance to create their objects
        # self.create_objects()

        self._glinitialized = True

    def OnReshape(self, width: int, height: int):
        """Reshape the OpenGL viewport based on the dimensions of the window."""

        # Zero values occasionally appear during window setup.  Ignore these until real values appear
        if width == 0 or height == 0:
            return

        self.SetCurrent(self.context)
        gl.glViewport(0, 0, width, height)
        # self.update_object_resize()

    def activate_context(self):
        """Set this widgets GL context as the current context"""
        self.SetCurrent(self.context)

    def clear(self):
        gl.glClearDepth(10000.0)
        gl.glClearColor(0, 0.1, 0, 1)
        gl.glClear(gl.GL_COLOR_BUFFER_BIT | gl.GL_DEPTH_BUFFER_BIT)

    def OnDraw(self, *args, **kwargs):
        """Draw the window."""
        # clear the context
        if not self.IsShown():
            return

        if not self._glinitialized:
            return

        self.activate_context()

        # This should be set by OnReshape, but it is not being called for some reason
        self.width, self.height = self.GetClientSize()
        extents = self.GetGLExtents()
        gl.glViewport(0, 0, extents[0], extents[1])

        # self.canvas.SetCurrent(GLPanel.SharedGLContext)
        gl.glClearDepth(10000.0)
        gl.glClearColor(0, 0.1, 0, 1)
        gl.glClear(gl.GL_COLOR_BUFFER_BIT | gl.GL_DEPTH_BUFFER_BIT)
        gl.glEnable(gl.GL_BLEND)
        gl.glEnable(gl.GL_POLYGON_OFFSET_FILL)
        gl.glEnable(gl.GL_DEPTH_TEST)
        gl.glDepthFunc(gl.GL_LESS)
        # gl.glDisable(gl.GL_DEPTH_TEST)
        gl.glDisable(gl.GL_CULL_FACE)
        # draw objects
        # self.draw_objects()
        self._draw_method()
        # update screen
        self.SwapBuffers()
