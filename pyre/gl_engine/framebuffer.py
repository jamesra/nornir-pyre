import OpenGL.GL as gl
from PyQt6.QtOpenGL import QOpenGLFunctions_4_1_Core as QOpenGLFunctions


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
        if client_size != self.size:
            self.free_fbo()

            self.size = client_size

            self._fbo = self.gl_funcs.glGenBuffers(1)
            self.gl_funcs.glBindFramebuffer(gl.GL_FRAMEBUFFER, self._fbo)

            self._fbo_texture = self._create_frame_buffer_texture(self.size)
            self.gl_funcs.glFramebufferTexture2D(gl.GL_FRAMEBUFFER,
                                                 gl.GL_COLOR_ATTACHMENT0,
                                                 gl.GL_TEXTURE_2D,
                                                 self._fbo_texture,
                                                 0)

            if self.gl_funcs.glCheckFramebufferStatus(gl.GL_FRAMEBUFFER) != gl.GL_FRAMEBUFFER_COMPLETE:
                raise RuntimeError("Framebuffer is not complete")

            # Unbind the frame buffer
            self.gl_funcs.glBindFramebuffer(gl.GL_FRAMEBUFFER, 0)

        return self._fbo

    def free_fbo(self):
        """Free the frame buffer and texture resources"""
        if self._fbo_texture is not None:
            self.gl_funcs.glDeleteTextures([self._fbo_texture])
            self._fbo_texture = None

        if self._fbo is not None:
            self.gl_funcs.glDeleteBuffers(1, [self._fbo])
            self._fbo = None

    def _create_frame_buffer_texture(self, size: tuple[int, int]) -> int:
        """Create a texture the size of our window that we can render onto"""
        height, width = size

        source_fbo_texture = self.gl_funcs.glGenTextures(1)
        self.gl_funcs.glBindTexture(gl.GL_TEXTURE_2D, source_fbo_texture)
        self.gl_funcs.glTexImage2D(gl.GL_TEXTURE_2D, 0, gl.GL_RGBA, width, height, 0, gl.GL_RGBA, gl.GL_UNSIGNED_BYTE,
                                   None)
        self.gl_funcs.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_NEAREST)
        self.gl_funcs.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_NEAREST)
        return source_fbo_texture

    def __del__(self):
        """Free our gl resources if we are deleted"""
        self.free_fbo()
