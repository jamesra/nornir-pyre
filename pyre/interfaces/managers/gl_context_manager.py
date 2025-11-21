from abc import ABC, abstractmethod
from typing import Callable

from PyQt6.QtGui import QOpenGLContext
from PyQt6.QtOpenGLWidgets import QOpenGLWidget

GLContextCreatedCallback = Callable[[QOpenGLContext], None]


class IGLContextManager(ABC):
    """This interface tracks when windows create a GL context.  All context's are
    assumed to be shared.  When a context is created, an event is raised with
    the context so subscribers can create GL resources."""

    @abstractmethod
    def add_context(self, context: QOpenGLContext, widget: QOpenGLWidget = None):
        """Add a context to the context manager. This should be called by the GLCanvas when a context is created.
        
        Args:
            context: The OpenGL context to add
            widget: The OpenGL widget associated with this context (optional but recommended for context activation)
        """
        raise NotImplementedError()

    @abstractmethod
    def add_glcontext_added_event_listener(self, func: GLContextCreatedCallback):
        """Callbacks are invoked when a GLContext is created, or if a context already exists,
         immediately upon registration."""
        raise NotImplementedError()

    @abstractmethod
    def remove_glcontext_added_event_listener(self, func: GLContextCreatedCallback):
        """Callbacks are invoked when a GLContext is created, or if a context already exists,
         immediately upon registration."""
        raise NotImplementedError()
