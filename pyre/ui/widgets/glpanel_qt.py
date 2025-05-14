#!/usr/bin/python

from typing import Callable

from dependency_injector.wiring import inject, Provide

import OpenGL.GL as gl
from PyQt6.QtWidgets import QWidget
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtOpenGL import QOpenGLFunctions_4_5_Core as QOpenGLFunctions
from PyQt6.QtCore import Qt, QSize, QPoint
from PyQt6.QtGui import QResizeEvent, QPaintEvent

from pyre.interfaces.managers.gl_context_manager import IGLContextManager
from pyre.container import IContainer


def cb_dbg_msg(source, msg_type, msg_id, severity, length, raw, user):
    msg = raw[0:length]
    print(f'debug: {source}, {msg_type}, {msg_id}, {severity}, {msg}')


# Create a ctypes callback instance
debug_callback_func = gl.GLDEBUGPROC(cb_dbg_msg)


class GLPanel(QOpenGLWidget):
    """A QT widget that contains an OpenGL canvas."""

    _glinitialized: bool = False
    _draw_method: Callable[[], None]  # Method we call to render scene onto our canvas

    SharedGLContext = None  # type: QOpenGLFunctions
    _glcontextmanager: IGLContextManager = Provide[IContainer.glcontext_manager]

    @inject
    def __init__(self,
                 parent: QWidget,
                 draw_method: Callable[[], None],
                 pos: QPoint = QPoint(),
                 size: QSize = QSize(),
                 **kwargs):
        self._draw_method = draw_method
        # call super function
        super(GLPanel, self).__init__(parent=parent, **kwargs)
        
        # Set focus policy to accept keyboard input
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        
        # Set position and size if provided
        if pos != QPoint():
            self.move(pos)
        if size != QSize():
            self.resize(size)

    def GetGLExtents(self):
        """Get the extents of the OpenGL canvas."""
        return self.size()

    def initializeGL(self):
        """
        Initialize OpenGL for use in the window.
        This is called automatically by QOpenGLWidget when the widget is first shown.
        """
        if self._glinitialized:
            return

        # Create shared context if it doesn't exist
        if GLPanel.SharedGLContext is None:
            GLPanel.SharedGLContext = QOpenGLFunctions()
            GLPanel.SharedGLContext.initializeOpenGLFunctions()
            
            # Install debug message callback
            gl.glDebugMessageCallback(debug_callback_func, None)
            gl.glEnable(gl.GL_DEBUG_OUTPUT)

        # Notify the context manager that a new context has been created
        self._glcontextmanager.add_context(self.context())

        self._glinitialized = True

    def resizeGL(self, width: int, height: int):
        """Reshape the OpenGL viewport based on the dimensions of the window."""
        # Zero values occasionally appear during window setup. Ignore these until real values appear
        if width == 0 or height == 0:
            return

        self.width, self.height = width, height
        gl.glViewport(0, 0, width, height)

    def paintGL(self):
        """Draw the window."""
        # clear the context
        if not self.isVisible():
            return

        if not self._glinitialized:
            return

        # This should be set by resizeGL, but ensure it's correct
        self.width, self.height = self.width(), self.height()
        extents = self.GetGLExtents()
        gl.glViewport(0, 0, extents.width(), extents.height())

        gl.glClearDepth(10000.0)
        gl.glClearColor(0, 0.1, 0, 1)
        gl.glClear(gl.GL_COLOR_BUFFER_BIT | gl.GL_DEPTH_BUFFER_BIT)
        gl.glEnable(gl.GL_BLEND)
        gl.glEnable(gl.GL_POLYGON_OFFSET_FILL)
        gl.glEnable(gl.GL_DEPTH_TEST)
        gl.glDepthFunc(gl.GL_LESS)
        gl.glDisable(gl.GL_CULL_FACE)
        
        # draw objects
        self._draw_method()

    def activate_context(self):
        """Set this widgets GL context as the current context"""
        self.makeCurrent()

    def clear(self):
        gl.glClearDepth(10000.0)
        gl.glClearColor(0, 0.1, 0, 1)
        gl.glClear(gl.GL_COLOR_BUFFER_BIT | gl.GL_DEPTH_BUFFER_BIT)