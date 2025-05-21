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

Functions:
    diagnose_gl_context_sharing: Diagnoses whether OpenGL contexts are properly shared.
"""

from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtGui import QOpenGLContext
from PyQt6.QtWidgets import QApplication
from PyQt6.QtOpenGL import QOpenGLTexture
import OpenGL.GL as gl

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
    """

    _GLContextAddedEventListeners: IEventManager[GLContextCreatedCallback]
    _known_contexts: list[QOpenGLContext]

    def __init__(self):
        self._GLContextAddedEventListeners = QtEventManager[GLContextCreatedCallback]()
        self._known_contexts = list()

    def add_context(self, context: QOpenGLContext):
        """
        Add a context to the manager and notify subscribers.

        This method adds the provided OpenGL context to the list of known contexts
        if it's not already present. It then invokes the diagnose_gl_context_sharing
        function to check context sharing and notifies all subscribers about the new context.

        Args:
            context: The OpenGL context to add to the manager

        Returns:
            None
        """
        if context not in self._known_contexts:
            print(f"Adding context {context}")

            self._known_contexts.append(context)

            diagnose_gl_context_sharing()
            self._GLContextAddedEventListeners.invoke(context)  # Notify all subscribers

    def add_glcontext_added_event_listener(self, func: GLContextCreatedCallback):
        """
        Subscribe to GL context creation events.

        Registers a callback function to be invoked when a new OpenGL context is created.
        If any contexts already exist when this method is called, the callback will be
        immediately invoked for each existing context.

        Args:
            func: Callback function to be invoked when a context is created.
                 The function should accept a QOpenGLContext parameter.

        Returns:
            None
        """
        self._GLContextAddedEventListeners.add(func)
        print(f"Adding context event listener {func}")
        for context in self._known_contexts:
            func(context)

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


def diagnose_gl_context_sharing():
    """
    Diagnose whether OpenGL contexts in the application are properly shared.

    This function performs a series of tests to determine if OpenGL contexts
    across different widgets are properly sharing resources. It:

    1. Finds all OpenGL widgets in the application
    2. Checks each widget's context and prints information about it
    3. Creates a test texture in each context to verify resource creation
    4. Tests cross-context resource access by creating a texture in one context
       and attempting to access it from other contexts

    This is useful for debugging OpenGL context sharing issues, which can cause
    resources to be duplicated or inaccessible across different parts of the application.

    Returns:
        None: Results are printed to the console
    """
    gl_widgets = []

    # Find all OpenGL widgets in the application
    for widget in QApplication.allWidgets():
        if isinstance(widget, QOpenGLWidget):
            gl_widgets.append(widget)

    print(f"Found {len(gl_widgets)} OpenGL widgets")

    if len(gl_widgets) < 2:
        return  # Not enough widgets to check sharing

    # Check each widget's context
    contexts = []
    for i, widget in enumerate(gl_widgets):
        widget.makeCurrent()
        context = QOpenGLContext.currentContext()
        contexts.append(context)

        # Print context info
        print(f"Widget {i}: Context {context}, share context: {context.shareContext()}")

        # Test by creating a resource
        try:
            texture_id = QOpenGLTexture()
            texture_id.textureId()
            print(f"  Created texture {texture_id.textureId()} in context {context}")
            del texture_id  # Clean up
        except Exception as e:
            print(f"  Failed to create texture: {e}")

        widget.doneCurrent()

    # Try to access resources across contexts
    if len(contexts) > 1:
        print("\nTesting cross-context resource access:")
        # Create test texture in first context
        gl_widgets[0].makeCurrent()
        test_texture = QOpenGLTexture()
        test_texture.bind()
        gl_widgets[0].doneCurrent()

        # Try to use texture in other contexts
        for i, widget in enumerate(gl_widgets[1:], 1):
            widget.makeCurrent()
            try:
                test_texture.bind()
                print(f"  Success: Widget {i} can access texture from Widget 0")
            except Exception as e:
                print(f"  Failure: Widget {i} cannot access texture from Widget 0: {e}")
            widget.doneCurrent()

        # Clean up
        gl_widgets[0].makeCurrent()
        del test_texture  # Clean up the test texture
        gl_widgets[0].doneCurrent()
