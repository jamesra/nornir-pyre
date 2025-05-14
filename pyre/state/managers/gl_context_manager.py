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

import wx.glcanvas

from pyre.eventmanager import wxEventManager
from pyre.interfaces import IEventManager
from pyre.interfaces.managers.gl_context_manager import GLContextCreatedCallback, IGLContextManager


class GLContextManager(IGLContextManager):
    """This class tracks when windows create a GL context.  All context's are
    assumed to be shared.  When a context is created, an event is raised with
    the context so subscribers can create GL resources."""

    _GLContextAddedEventListeners: IEventManager[GLContextCreatedCallback]
    _known_contexts: list[wx.glcanvas.GLContext]

    def __init__(self):
        self._GLContextAddedEventListeners = wxEventManager[GLContextCreatedCallback]()
        self._known_contexts = list()

    def add_context(self, context: wx.glcanvas.GLContext):
        """Add a context to the manager.  This will invoke all subscribers with the new context."""
        if context not in self._known_contexts:
            print(f"Adding context {context}")
            self._known_contexts.append(context)
            self._GLContextAddedEventListeners.invoke(context)  # Notify all subscribers

    def add_glcontext_added_event_listener(self, func: GLContextCreatedCallback):
        """Callbacks are invoked when a GLContext is created, or if a context already exists,
                immediately upon registration."""
        self._GLContextAddedEventListeners.add(func)
        print(f"Adding context event listener {func}")
        for context in self._known_contexts:
            func(context)

    def remove_glcontext_added_event_listener(self, func: GLContextCreatedCallback):
        """Unsubscribe from context events"""
        self._GLContextAddedEventListeners.remove(func)
