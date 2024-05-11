from OpenGL import GL as gl


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
