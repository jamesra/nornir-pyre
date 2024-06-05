"""
This module tracks when windows create a GL context.  This the rough order of context creation:
1. Create the frame, which will create a GLPanel during initialization.
2. The GLPanel will send a wx.EVT_GL_CONTEXT_CREATED event to the frame.  This allows the frame to complete
    intitialization before GL objects are created.
3. Upon receiving the event, the GLPanel will call OnInitGL() to initialize OpenGL.  It will then
    notify the GLContextManager that a new context has been created.
4. The GLContextManager will notify all subscribers that a new context has been created.
5. GLPanel then invokes create_objects() so anyone inheriting GLPanel can perform initialization.
"""

from abc import ABC, abstractmethod
from typing import Callable
import OpenGL as gl
import wx.glcanvas

GLContextCreatedCallback = Callable[[wx.glcanvas.GLContext], None]


class IGLContextManager(ABC):
    """This interface tracks when windows create a GL context.  All context's are
    assumed to be shared.  When a context is created, an event is raised with
    the context so subscribers can create GL resources."""

    @abstractmethod
    def add_context(self, context: wx.glcanvas.GLContext):
        """Add a context to the context manager. This should be called by the GLCanvas when a context is created."""
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


class GLContextManager(IGLContextManager):
    """This class tracks when windows create a GL context.  All context's are
    assumed to be shared.  When a context is created, an event is raised with
    the context so subscribers can create GL resources."""

    _GLContextAddedEventListeners: list[GLContextCreatedCallback] = []
    _known_contexts: set[wx.glcanvas.GLContext] = set()

    def add_context(self, context: wx.glcanvas.GLContext):
        """Add a context to the manager.  This will invoke all subscribers with the new context."""
        if context not in self._known_contexts:
            self._known_contexts.add(context)
            for listener in self._GLContextAddedEventListeners:
                listener(context)

    def add_glcontext_added_event_listener(self, func: GLContextCreatedCallback):
        """Callbacks are invoked when a GLContext is created, or if a context already exists,
                immediately upon registration."""
        self._GLContextAddedEventListeners.append(func)
        for context in self._known_contexts:
            func(context)

    def remove_glcontext_added_event_listener(self, func: GLContextCreatedCallback):
        """Unsubscribe from context events"""
        self._GLContextAddedEventListeners.remove(func)
