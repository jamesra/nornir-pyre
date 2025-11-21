"""
This module tracks when windows create a GL context and manages context sharing.

The module follows this sequence for context creation:
1. Create the frame, which will create a GLPanel during initialization.
2. The GLPanel will send a context created event to the frame, allowing the frame to complete
   initialization before GL objects are created.
3. Upon receiving the event, the GLPanel will initialize OpenGL and then
   notify the GLContextManager that a new context has been created.
4. The GLContextManager will notify all subscribers that a new context has been created.
5. GLPanel then invokes create_objects() so anyone inheriting GLPanel can perform initialization.

This module is essential for ensuring proper OpenGL context management across multiple windows
and for enabling resource sharing between contexts.

Classes:
    GLContextManager: Manages OpenGL contexts and notifies subscribers when new contexts are created.
"""

from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtGui import QOpenGLContext
import OpenGL.GL as gl

import nornir_imageregistration
from pyre.qt_eventmanager import QtEventManager
from pyre.interfaces import IEventManager
from pyre.interfaces.managers.gl_context_manager import GLContextCreatedCallback, IGLContextManager


class GLContextManager(IGLContextManager):
    """
    Manages OpenGL contexts and notifies subscribers when new contexts are created.

    This class tracks when windows create a GL context. All contexts are
    assumed to be shared. When a context is created, an event is raised with
    the context so subscribers can create GL resources.

    The manager maintains a list of known contexts and provides methods for
    subscribing to context creation events. When a new context is added,
    all subscribers are notified.

    Attributes:
        _GLContextAddedEventListeners: Event manager for context creation callbacks
        _known_contexts: List of known OpenGL contexts
        _context_to_widget: Mapping from context to widget for making contexts current
    """

    _GLContextAddedEventListeners: IEventManager[GLContextCreatedCallback]
    _known_contexts: list[QOpenGLContext]
    _context_to_widget: dict[QOpenGLContext, QOpenGLWidget]

    def __init__(self):
        self._GLContextAddedEventListeners = QtEventManager[GLContextCreatedCallback]()
        self._known_contexts = list()
        self._context_to_widget = {}

    def add_context(self, context: QOpenGLContext, widget: QOpenGLWidget = None):
        """
        Add a context to the manager and notify subscribers.

        This method adds the provided OpenGL context to the list of known contexts
        if it's not already present. It stores the widget reference for making the
        context current when needed. It then notifies all subscribers about the new context.

        The context is made current before notifying subscribers to ensure they can create
        OpenGL objects safely.

        Args:
            context: The OpenGL context to add to the manager
            widget: The OpenGL widget associated with this context (optional but recommended)

        Returns:
            None
        """
        if context not in self._known_contexts:
            print(f"Adding context {context}")

            self._known_contexts.append(context)
            if widget is not None:
                self._context_to_widget[context] = widget

            # Ensure context is current before invoking callbacks
            # This is critical - callbacks will create OpenGL objects that require a current context
            # Note: When called from initializeGL, Qt should already have made the context current
            if widget is not None:
                current_before_invoke = QOpenGLContext.currentContext()
                if current_before_invoke == context:
                    # Context is already current (e.g., from initializeGL) - no need to make it current
                    context_was_restored = False
                else:
                    # Try to make the context current
                    # Note: makeCurrent() may fail if widget is not visible yet
                    if widget.makeCurrent():
                        # Verify it's actually current now
                        current_context = QOpenGLContext.currentContext()
                        if current_context != context:
                            # Context mismatch - restore and skip callbacks for now
                            widget.doneCurrent()
                            print(f"Warning: Context mismatch in add_context. "
                                  f"Widget visible: {widget.isVisible()}, Context valid: {context.isValid()}. "
                                  f"Callbacks will be invoked when widget becomes visible.")
                            return  # Skip callback invocation - they'll be called when widget is visible
                        context_was_restored = True  # Track that we made it current
                    else:
                        # makeCurrent() failed - this can happen if widget is not visible yet
                        # Don't fail, just skip callbacks for now - they'll be invoked when visible
                        print(f"Warning: Failed to make context current in add_context. "
                              f"Widget visible: {widget.isVisible()}, Context valid: {context.isValid()}. "
                              f"Callbacks will be invoked when widget becomes visible.")
                        return  # Skip callback invocation
            else:
                # No widget provided - this shouldn't happen during initialization
                raise RuntimeError(
                    f"Cannot make context current: no widget provided in add_context. "
                    f"Context: {context}, Current: {QOpenGLContext.currentContext()}"
                )
            
            # Check for any OpenGL errors before invoking callbacks
            # We should have a current context at this point
            # Use raise_on_error to find the source of any errors, not just clear them
            from pyre.gl_engine.helpers import raise_on_error
            raise_on_error("before invoking context-added callbacks in add_context - checking for prior errors")
            
            # Validate the context is actually functional by trying a simple operation
            # This ensures we don't invoke callbacks with a broken context
            try:
                import OpenGL.GL as gl
                # Try a simple query that requires a valid context
                version = gl.glGetString(gl.GL_VERSION)
                if version is None:
                    raise RuntimeError("Context appears non-functional: glGetString(GL_VERSION) returned None")
            except Exception as e:
                raise RuntimeError(
                    f"Context validation failed before invoking callbacks: {e}. "
                    f"Context may be in an error state or not properly initialized."
                ) from e
            
            try:
                # Invoke callbacks - context must be current for OpenGL operations in callbacks
                self._GLContextAddedEventListeners.invoke(context)  # Notify all subscribers
            finally:
                # Only release if we made it current (either from diagnostic restore or before invoke)
                # Don't release if it was already current from initializeGL
                if context_was_restored and widget is not None:
                    widget.doneCurrent()

    def add_glcontext_added_event_listener(self, func: GLContextCreatedCallback):
        """
        Subscribe to GL context creation events.

        Registers a callback function to be invoked when a new OpenGL context is created.
        If any contexts already exist when this method is called, the callback will be
        immediately invoked for each existing context. The context is made current before
        invoking the callback to ensure OpenGL operations can be performed safely.

        Args:
            func: Callback function to be invoked when a context is created.
                 The function should accept a QOpenGLContext parameter.

        Returns:
            None
        """
        self._GLContextAddedEventListeners.add(func)
        print(f"Adding context event listener {func}")
        for context in self._known_contexts:
            # Make the context current before invoking the callback
            widget = self._context_to_widget.get(context)
            if widget is None:
                print(f"Warning: No widget for context {context}, callback may fail")
                func(context)
                continue
                
            # Check if context is already current
            current_context = QOpenGLContext.currentContext()
            was_current = (current_context == context)
            
            if not was_current:
                print(f"Making context current for existing context callback")
                widget.makeCurrent()
            
            try:
                func(context)
            finally:
                # Only release if we made it current (not if it was already current)
                if not was_current:
                    widget.doneCurrent()

    def remove_glcontext_added_event_listener(self, func: GLContextCreatedCallback):
        """
        Unsubscribe from GL context creation events.

        Removes a previously registered callback function from the list of subscribers.
        The function will no longer be invoked when new OpenGL contexts are created.

        Args:
            func: The callback function to remove from the subscription list.
                 This should be the same function reference that was previously
                 passed to add_glcontext_added_event_listener.

        Returns:
            None
        """
        self._GLContextAddedEventListeners.remove(func)
