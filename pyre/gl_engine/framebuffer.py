import OpenGL.GL as gl
from PyQt6.QtOpenGL import QOpenGLFunctions_4_1_Core as QOpenGLFunctions

from pyre.gl_engine.helpers import raise_on_error, check_for_error


class FrameBuffer:
    """Holds a frame buffer object for rendering to a texture.
       The texture will be replaced if the client size changes.
    """
    _size: tuple[int, int]  # Size of the frame buffer
    _fbo_texture: int | None  # Frame buffer object's texture
    _fbo: int | None  # Frame buffer object
    _gl_funcs: QOpenGLFunctions  # OpenGL functions

    @property
    def gl_funcs(self) -> QOpenGLFunctions:
        """The OpenGL functions used to create the frame buffer"""
        if self._gl_funcs is None:
            self._gl_funcs = QOpenGLFunctions()
            self._gl_funcs.initializeOpenGLFunctions()
        return self._gl_funcs

    @property
    def fbo_texture(self) -> int:
        """The texture that is rendered to by the frame buffer"""
        return self._fbo_texture

    def __init__(self, gl_funcs: QOpenGLFunctions):
        self.size = (0, 0)
        self._fbo = None
        self._fbo_texture = None
        self._gl_funcs = gl_funcs

    def get_or_create_fbo(self, client_size: tuple[int, int]) -> int:
        """Create a frame buffer if the size has changed.  Otherwise use the existing frame buffer"""
        if client_size != self.size or self._fbo is None:
            self.free_fbo()

            self.size = client_size

            # Clear any previous errors before creating framebuffer
            check_for_error("before glGenFramebuffers in get_or_create_fbo")
            
            # Qt's QOpenGLFunctions may not have glGenFramebuffers, use raw OpenGL
            # glGenFramebuffers(1) returns a single integer (numpy.uintc), convert to int
            fbo_id = gl.glGenFramebuffers(1)
            raise_on_error("after glGenFramebuffers in get_or_create_fbo")
            if fbo_id is None or fbo_id == 0:
                raise RuntimeError("Failed to generate framebuffer")
            self._fbo = int(fbo_id)  # Convert numpy.uintc to int for compatibility
            gl.glBindFramebuffer(gl.GL_FRAMEBUFFER, self._fbo)
            raise_on_error("after glBindFramebuffer in get_or_create_fbo")

            self._fbo_texture = self._create_frame_buffer_texture(self.size)
            # Use raw OpenGL for framebuffer operations
            gl.glFramebufferTexture2D(gl.GL_FRAMEBUFFER,
                                      gl.GL_COLOR_ATTACHMENT0,
                                      gl.GL_TEXTURE_2D,
                                      self._fbo_texture,
                                      0)
            raise_on_error("after glFramebufferTexture2D in get_or_create_fbo")

            if gl.glCheckFramebufferStatus(gl.GL_FRAMEBUFFER) != gl.GL_FRAMEBUFFER_COMPLETE:
                raise RuntimeError("Framebuffer is not complete")

            # Unbind the frame buffer
            gl.glBindFramebuffer(gl.GL_FRAMEBUFFER, 0)
            raise_on_error("after glBindFramebuffer(0) in get_or_create_fbo")

        return self._fbo

    def free_fbo(self):
        """Free the frame buffer and texture resources"""
        if self._fbo_texture is not None:
            # PyQt6's glDeleteTextures expects (n, textures) like glDeleteBuffers
            self.gl_funcs.glDeleteTextures(1, [self._fbo_texture])
            check_for_error("after glDeleteTextures in free_fbo")
            self._fbo_texture = None

        if self._fbo is not None:
            # Use raw OpenGL for framebuffer deletion
            gl.glDeleteFramebuffers(1, [self._fbo])
            check_for_error("after glDeleteFramebuffers in free_fbo")
            self._fbo = None

    def _create_frame_buffer_texture(self, size: tuple[int, int]) -> int:
        """Create a texture the size of our window that we can render onto"""
        height, width = size

        # Use raw OpenGL for texture creation (Qt's wrapper may have issues)
        # glGenTextures(1) returns a single integer (numpy.uintc), convert to int
        texture_id = gl.glGenTextures(1)
        raise_on_error("after glGenTextures in _create_frame_buffer_texture")
        if texture_id is None or texture_id == 0:
            raise RuntimeError("Failed to generate framebuffer texture")
        source_fbo_texture = int(texture_id)  # Convert numpy.uintc to int for compatibility
        gl.glBindTexture(gl.GL_TEXTURE_2D, source_fbo_texture)
        raise_on_error("after glBindTexture in _create_frame_buffer_texture")
        gl.glTexImage2D(gl.GL_TEXTURE_2D, 0, gl.GL_RGBA, width, height, 0, gl.GL_RGBA, gl.GL_UNSIGNED_BYTE,
                       None)
        raise_on_error("after glTexImage2D in _create_frame_buffer_texture")
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_NEAREST)
        raise_on_error("after glTexParameteri(MAG_FILTER) in _create_frame_buffer_texture")
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_NEAREST)
        raise_on_error("after glTexParameteri(MIN_FILTER) in _create_frame_buffer_texture")
        return source_fbo_texture

    def __del__(self):
        """Free our gl resources if we are deleted"""
        self.free_fbo()
