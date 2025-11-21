#!/usr/bin/python

from typing import Callable

from dependency_injector.wiring import inject, Provide

import OpenGL.GL as gl
from PyQt6.QtWidgets import QWidget
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtOpenGL import QOpenGLFunctions_4_1_Core as QOpenGLFunctions
from PyQt6.QtCore import Qt, QSize, QPoint, QTimer
from PyQt6.QtGui import QResizeEvent, QPaintEvent
from PyQt6.QtGui import QSurfaceFormat, QOpenGLContext

from pyre.interfaces.managers.gl_context_manager import IGLContextManager
from pyre.container import IContainer
from pyre.gl_engine.helpers import check_for_error, raise_on_error

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
    _gl_funcs: QOpenGLFunctions = None

    @property
    def gl_funcs(self) -> QOpenGLFunctions:
        """Get the OpenGL functions for this context"""
        if not self._glinitialized:
            raise RuntimeError("OpenGL functions not initialized")
        return self._gl_funcs

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
        All OpenGL initialization should happen here to avoid race conditions.
        """
        if self._glinitialized:
            return

        # In debug mode, validate that we have a valid OpenGL context
        if nornir_imageregistration.in_debug_mode():
            context = self.context()
            if context is None:
                raise RuntimeError("initializeGL called but context() is None")
            
            if not context.isValid():
                raise RuntimeError("initializeGL called but context is not valid")
            
            # QOpenGLWidget should already have made the context current when initializeGL is called
            # Check if it's already current first
            current_context = QOpenGLContext.currentContext()
            if current_context != context:
                # Try to make it current if it's not
                if not self.makeCurrent():
                    raise RuntimeError(
                        f"initializeGL: Failed to make context current. "
                        f"Widget visible: {self.isVisible()}, "
                        f"Context valid: {context.isValid()}, "
                        f"Current context: {current_context}"
                    )
                # Verify it's now current
                current_context = QOpenGLContext.currentContext()
                if current_context != context:
                    raise RuntimeError(
                        f"initializeGL: Context mismatch after makeCurrent(). "
                        f"Expected {context}, got {current_context}"
                    )
            
            # Verify we can query OpenGL state (basic validation)
            try:
                # Try a simple OpenGL query to ensure the context is functional
                version = gl.glGetString(gl.GL_VERSION)
                if version is None:
                    raise RuntimeError("initializeGL: Failed to query OpenGL version - context may not be functional")
            except Exception as e:
                raise RuntimeError(f"initializeGL: OpenGL context validation failed: {e}") from e

        # Initialize OpenGL functions first
        self._gl_funcs = QOpenGLFunctions()
        self._gl_funcs.initializeOpenGLFunctions()

        # Create shared context if it doesn't exist
        if GLPanel.SharedContext is None:
            GLPanel.SharedContext = self.initialize_shared_context()

            # Install debug message callback
            if nornir_imageregistration.in_debug_mode():
                self._gl_funcs.glDebugMessageCallback(debug_callback_func, None)
                self._gl_funcs.glEnable(gl.GL_DEBUG_OUTPUT)

        # Set share context and notify the context manager
        self.context().setShareContext(GLPanel.SharedContext)
        self._glcontextmanager.add_context(self.context(), self)

        self._glinitialized = True
        print(f"OpenGL initialized for widget {self}")

    def resizeGL(self, width: int, height: int):
        """Reshape the OpenGL viewport based on the dimensions of the window."""
        # Zero values occasionally appear during window setup. Ignore these until real values appear
        if width == 0 or height == 0:
            return

        if not self._glinitialized:
            return

        # Get the device pixel ratio to account for high-DPI displays
        pixel_ratio = self.devicePixelRatio()

        # Scale the viewport dimensions by the pixel ratio
        physical_width = int(width * pixel_ratio)
        physical_height = int(height * pixel_ratio)

        # Scale the viewport dimensions by the pixel ratio
        viewport_dims = self.gl_funcs.glGetIntegerv(gl.GL_MAX_VIEWPORT_DIMS)

        max_width, max_height = viewport_dims

        physical_width = max(1, min(physical_width, max_width))
        physical_height = max(1, min(physical_height, max_height))

        # Update the viewport with the physical pixel dimensions
        self.gl_funcs.glViewport(0, 0, physical_width, physical_height)
        check_for_error("after glViewport in resizeGL")

    def paintGL(self):
        """Draw the window."""
        # Don't check isVisible() - Qt calls paintGL when needed
        # The visibility check was preventing rendering even when windows were shown

        if not self._glinitialized:
            return

        if self._gl_funcs is None:
            return

        # Activate context and verify it's current
        self.activate_context()
        
        # Verify context is actually current
        current_context = QOpenGLContext.currentContext()
        if not current_context or current_context != self.context():
            print(f"WARNING: Context not current in paintGL. Expected {self.context()}, got {current_context}")
            return

        # This should be set by resizeGL, but ensure it's correct
        extents = self.GetGLExtents()
        pixel_ratio = self.devicePixelRatio()

        physical_width = int(extents.width() * pixel_ratio)
        physical_height = int(extents.height() * pixel_ratio)

        # Create/get OpenGL functions for this context

        # Check for errors from previous operations - this will raise if there's an error
        # This helps us find what's causing GL_INVALID_ENUM at the start of paintGL
        raise_on_error("at start of paintGL - checking for prior errors")

        # Use the QOpenGLFunctions interface directly
        # Note: Some of these might not be valid in all OpenGL contexts
        # Use try/except to handle gracefully

        self._gl_funcs.glEnable(gl.GL_BLEND)
        raise_on_error("after glEnable(GL_BLEND)")
        # GL_POLYGON_OFFSET_FILL - enable polygon offset fill (not a capability enum issue, but check for errors)
        self._gl_funcs.glEnable(gl.GL_POLYGON_OFFSET_FILL)
        raise_on_error("after glEnable(GL_POLYGON_OFFSET_FILL)")
        self._gl_funcs.glEnable(gl.GL_DEPTH_TEST)
        raise_on_error("after glEnable(GL_DEPTH_TEST)")
        self._gl_funcs.glDepthFunc(gl.GL_LESS)
        raise_on_error("after glDepthFunc")
        self._gl_funcs.glDisable(gl.GL_CULL_FACE)
        raise_on_error("after glDisable(GL_CULL_FACE)")

        self.clear()
        raise_on_error("after clear()")

        # draw objects - wrap in error handling 
        self._draw_method()
         

    def activate_context(self):
        """Set this widgets GL context as the current context"""
        self.makeCurrent()

    def clear(self): 
        self._gl_funcs.glClearDepthf(1)
        check_for_error("after glClearDepthf in clear()")
        self._gl_funcs.glClearColor(0, 0.1, 0, 1)
        check_for_error("after glClearColor in clear()")
        self._gl_funcs.glClear(gl.GL_COLOR_BUFFER_BIT | gl.GL_DEPTH_BUFFER_BIT)
        check_for_error("after glClear in clear()")
