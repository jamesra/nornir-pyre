#!/usr/bin/python

from typing import Callable

from dependency_injector.wiring import inject, Provide

import OpenGL.GL as gl
from PyQt6.QtWidgets import QWidget
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtOpenGL import QOpenGLFunctions_4_1_Core as QOpenGLFunctions
from PyQt6.QtCore import Qt, QSize, QPoint
from PyQt6.QtGui import QResizeEvent, QPaintEvent
from PyQt6.QtGui import QSurfaceFormat, QOpenGLContext

from pyre.interfaces.managers.gl_context_manager import IGLContextManager
from pyre.container import IContainer

import nornir_imageregistration


def cb_dbg_msg(source, msg_type, msg_id, severity, length, raw, user):
    msg = raw[0:length]
    print(f'debug: {source}, {msg_type}, {msg_id}, {severity}, {msg}')


# Create a ctypes callback instance
debug_callback_func = gl.GLDEBUGPROC(cb_dbg_msg)


class GLPanel(QOpenGLWidget):
    """A QT widget that contains an OpenGL canvas."""
    # Add this as a class variable to store the shared context
    SharedContext = None  # type: QOpenGLContext

    _glinitialized: bool = False
    _draw_method: Callable[[], None]  # Method we call to render scene onto our canvas
    _glcontextmanager: IGLContextManager = Provide[IContainer.glcontext_manager]

    @classmethod
    def initialize_shared_context(cls):
        if cls.SharedContext is None:
            # Create shared context
            cls.SharedContext = QOpenGLContext()
            cls.SharedContext.setFormat(QSurfaceFormat.defaultFormat())
            cls.SharedContext.create()

        return cls.SharedContext

    @inject
    def __init__(self, parent, draw_method, pos=QPoint(), size=QSize(), **kwargs):
        # Initialize shared context if not already done
        self._draw_method = draw_method
        super(GLPanel, self).__init__(parent=parent, **kwargs)
        self.__class__.initialize_shared_context()

        # Set format
        self.setFormat(QSurfaceFormat.defaultFormat())

        # # Create context that shares with SharedContext
        # context = QOpenGLContext(self)
        # context.setFormat(self.format())
        # context.setShareContext(GLPanel.SharedContext)
        # context.create()
        #
        # # Set this context for the widget
        # self.setContext(context)

        # Rest of your initialization code...

        # Set focus policy to accept keyboard input
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Set position and size if provided
        if pos != QPoint():
            self.move(pos)
        if size != QSize():
            self.resize(size)

    #
    # def setContext(self, context):
    #     """Set the OpenGL context for this widget"""
    #     self.context = context
    #
    #     # If the widget is already initialized, make sure to makeCurrent() with the new context
    #     if self.isValid():
    #         self.makeCurrent()

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
        if GLPanel.SharedContext is None:
            GLPanel.SharedContext = self.initialize_shared_context()

            # Install debug message callback
            if nornir_imageregistration.in_debug_mode():
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

        # Get the device pixel ratio to account for high-DPI displays
        pixel_ratio = self.devicePixelRatio()

        # Scale the viewport dimensions by the pixel ratio
        physical_width = int(width * pixel_ratio)
        physical_height = int(height * pixel_ratio)

        # Update the viewport with the physical pixel dimensions
        gl.glViewport(0, 0, physical_width, physical_height)

    def paintGL(self):
        """Draw the window."""
        # clear the context
        if not self.isVisible():
            return

        if not self._glinitialized:
            return

        # This should be set by resizeGL, but ensure it's correct
        extents = self.GetGLExtents()
        pixel_ratio = self.devicePixelRatio()

        # Scale the viewport dimensions by the pixel ratio
        physical_width = int(extents.width() * pixel_ratio)
        physical_height = int(extents.height() * pixel_ratio)

        gl.glViewport(0, 0, physical_width, physical_height)

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
