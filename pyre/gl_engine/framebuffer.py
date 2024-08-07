import OpenGL.GL as gl


class FrameBuffer:
    """Holds a frame buffer object for rendering to a texture.
       The texture will be replaced if the client size changes.
    """
    _size: tuple[int, int]  # Size of the frame buffer
    _fbo_texture: int | None  # Frame buffer object's texture
    _fbo: int | None  # Frame buffer object

    @property
    def fbo_texture(self) -> int:
        """The texture that is rendered to by the frame buffer"""
        return self._fbo_texture

    def __init__(self):
        self.size = (0, 0)
        self._fbo = None
        self._fbo_texture = None

    def get_or_create_fbo(self, client_size: tuple[int, int]) -> int:
        """Create a frame buffer if the size has changed.  Otherwise use the existing frame buffer"""
        if client_size != self.size:
            self.free_fbo()

            self.size = client_size

            self._fbo = gl.glGenFramebuffers(1)
            gl.glBindFramebuffer(gl.GL_FRAMEBUFFER, self._fbo)

            self._fbo_texture = self._create_frame_buffer_texture(self.size)
            gl.glFramebufferTexture2D(gl.GL_FRAMEBUFFER,
                                      gl.GL_COLOR_ATTACHMENT0,
                                      gl.GL_TEXTURE_2D,
                                      self._fbo_texture,
                                      0)

            if gl.glCheckFramebufferStatus(gl.GL_FRAMEBUFFER) != gl.GL_FRAMEBUFFER_COMPLETE:
                raise RuntimeError("Framebuffer is not complete")

            # Unbind the frame buffer
            gl.glBindFramebuffer(gl.GL_FRAMEBUFFER, 0)

        return self._fbo

    def free_fbo(self):
        """Free the frame buffer and texture resources"""
        if self._fbo_texture is not None:
            gl.glDeleteTextures([self._fbo_texture])
            self._fbo_texture = None

        if self._fbo is not None:
            gl.glDeleteFramebuffers(1, [self._fbo])
            self._fbo = None

    @staticmethod
    def _create_frame_buffer_texture(size: tuple[int, int]) -> int:
        """Create a texture the size of our window that we can render onto"""
        height, width = size

        source_fbo_texture = gl.glGenTextures(1)
        gl.glBindTexture(gl.GL_TEXTURE_2D, source_fbo_texture)
        gl.glTexImage2D(gl.GL_TEXTURE_2D, 0, gl.GL_RGBA, width, height, 0, gl.GL_RGBA, gl.GL_UNSIGNED_BYTE,
                        None)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_NEAREST)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_NEAREST)
        return source_fbo_texture

    def __del__(self):
        """Free our gl resources if we are deleted"""
        self.free_fbo()
