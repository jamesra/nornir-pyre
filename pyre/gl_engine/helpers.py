from OpenGL import GL as gl
from typing import Callable, cast
import logging
import numpy as np
from numpy.typing import NDArray
from PyQt6.QtCore import QCoreApplication, Qt
from PyQt6.QtGui import QOpenGLContext
from nornir_imageregistration import in_debug_mode

logger = logging.getLogger(__name__)


def gl_context_is_current() -> bool:
    """True when some OpenGL context is current on this thread."""
    return QOpenGLContext.currentContext() is not None


def context_sharing_enabled() -> bool:
    """True when ``AA_ShareOpenGLContexts`` is active for this application.

    Pyre compiles each shader program once at module level and caches its attrib and
    uniform locations, then uses them from every STOS panel. That is only valid because
    programs, shaders, buffers and textures are *shared* objects: with context sharing on,
    a name from one context is the same object in another. VAOs and framebuffers are
    container objects, which the OpenGL specification excludes from sharing, which is why
    those alone are tracked per context (see ContextAwareVAOHelper).

    Qt ignores the attribute if it is set after the QApplication exists, so this reports
    the effective state rather than what was requested.
    """
    return QCoreApplication.testAttribute(
        Qt.ApplicationAttribute.AA_ShareOpenGLContexts)


def delete_gl_object_on_teardown(delete: Callable[[], None], description: str) -> bool:
    """Run a ``glDelete*`` from a ``__del__`` without raising and without hiding a leak.

    ``__del__`` runs at an arbitrary point, often during interpreter or widget teardown when
    no context is current. A ``glDelete*`` issued then cannot reach the driver, so calling it
    anyway either raises (which Python turns into "Exception ignored in __del__") or is
    swallowed, in both cases leaving the object leaked with no record of it.

    :return: True when the delete was issued, False when it was skipped or failed. A False
        return means the GL object is leaked until its context is destroyed.
    """
    if not gl_context_is_current():
        logger.warning("no current OpenGL context during teardown; leaked %s", description)
        return False

    try:
        delete()
        return True
    except Exception as e:
        logger.warning("failed to delete %s during teardown: %s", description, e)
        return False


def raise_on_error(message: str | None = None, exception: Exception | None = None) -> None:
    """
    Raises an exception if an OpenGL error has occurred.
    
    This function should be called AFTER a GL operation to check for errors.
    Always checks for errors to ensure they are caught immediately.
    
    Args:
        message: Optional context message to include in the exception (e.g., "after glBindVertexArray")
        exception: Optional exception to chain as the cause
    """
    error = gl.glGetError()
    if error != gl.GL_NO_ERROR:
        error_name = get_gl_error_name(cast(int, error))
        if message:
            raise RuntimeError(f"OpenGL error {message}: {error_name} ({error})") from exception
        else:
            raise RuntimeError(f"OpenGL error: {error_name} ({error})") from exception


def check_for_error(message: str | None = None) -> bool:
    """
    Checks for OpenGL errors after a GL operation, logs them, and clears the error queue.
    
    This function should be called AFTER a GL operation to check for errors.
    If an error is found, it is logged and cleared. Does NOT raise exceptions.
    Used for non-critical operations where we want to log but continue.
    
    Args:
        message: Optional context message to include in the log (e.g., "after glBindVertexArray")
        
    Returns:
        True if an error was found, False otherwise. Callers can use this to abort further work if needed.
    """

    def try_log_error(error: int, message: str | None):
        """
        A helper function to log an error
        :param error: Error number
        :param message: Optional message
        :return: None
        """
        if error != gl.GL_NO_ERROR:
            error_name = get_gl_error_name(error)
            if message:
                logger.error("OpenGL error %s: %s (%s)", message, error_name, error)
            else:
                logger.error("OpenGL error: %s (%s)", error_name, error)

    found_error = False
    error = gl.glGetError()
    # Clear all remaining errors from the queue
    while error != gl.GL_NO_ERROR:
        found_error = True
        try_log_error(cast(int, error), message)
        error = gl.glGetError()

    return found_error


def get_gl_error_name(error_code: int) -> str:
    """Get a human-readable name for an OpenGL error code."""
    error_names = {
        gl.GL_NO_ERROR: "GL_NO_ERROR",
        gl.GL_INVALID_ENUM: "GL_INVALID_ENUM",
        gl.GL_INVALID_VALUE: "GL_INVALID_VALUE",
        gl.GL_INVALID_OPERATION: "GL_INVALID_OPERATION",
        gl.GL_INVALID_FRAMEBUFFER_OPERATION: "GL_INVALID_FRAMEBUFFER_OPERATION",
        gl.GL_OUT_OF_MEMORY: "GL_OUT_OF_MEMORY",
        gl.GL_STACK_OVERFLOW: "GL_STACK_OVERFLOW",
        gl.GL_STACK_UNDERFLOW: "GL_STACK_UNDERFLOW",
    }
    return error_names.get(error_code, f"Unknown error {error_code}")


def get_gl_type_size(gl_type: int) -> int:
    """Return the size of the GL type in bytes"""
    if gl_type == gl.GL_FLOAT:
        return 4
    elif gl_type == gl.GL_DOUBLE:
        return 8
    elif gl_type == gl.GL_INT or gl_type == gl.GL_UNSIGNED_INT:
        return 4
    elif gl_type == gl.GL_SHORT or gl_type == gl.GL_UNSIGNED_SHORT:
        return 2
    elif gl_type == gl.GL_BYTE or gl_type == gl.GL_UNSIGNED_BYTE:
        return 1
    else:
        raise ValueError(f"Unsupported GL type: {gl_type}")


def get_dtype_for_gl_type(gl_type: int) -> type[np.generic]:
    """Returns the numpy data type for the GL type"""
    if gl_type == gl.GL_FLOAT:
        return np.float32
    elif gl_type == gl.GL_DOUBLE:
        return np.float64
    elif gl_type == gl.GL_INT:
        return np.int32
    elif gl_type == gl.GL_UNSIGNED_INT:
        return np.uint32
    elif gl_type == gl.GL_SHORT:
        return np.int16
    elif gl_type == gl.GL_UNSIGNED_SHORT:
        return np.uint16
    elif gl_type == gl.GL_BYTE:
        return np.int8
    elif gl_type == gl.GL_UNSIGNED_BYTE:
        return np.uint8
    else:
        raise ValueError("Unsupported type")
