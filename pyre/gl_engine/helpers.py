from OpenGL import GL as gl
import numpy as np


def check_for_error():
    """Raises an exception if an OpenGL error has occurred."""
    error = gl.glGetError()
    if error != gl.GL_NO_ERROR:
        raise ValueError(f"OpenGL error: {error}")


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


def get_dtype_for_gl_type(gl_type: int) -> np.dtype:
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
