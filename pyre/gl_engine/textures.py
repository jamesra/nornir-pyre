import OpenGL.GL as gl
import numpy as np
from numpy.typing import NDArray


#
# def TextureForGrayscaleImage(image: NDArray[np.floating]):
#     '''Create a gl texture for the scipy.ndimage array'''
#
#     image = np.array(image, dtype=np.byte)
#     textureid = glGenTextures(1)
#     glBindTexture(GL_TEXTURE_2D, textureid)
#     glPixelStorei(GL_UNPACK_ALIGNMENT, 1)
#     swizzle_mask = (GL_RED, GL_RED, GL_RED, GL_ONE)
#     glTexParameteriv(GL_TEXTURE_2D, GL_TEXTURE_SWIZZLE_RGBA, swizzle_mask)
#     glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_BORDER)
#     glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_BORDER)
#     glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
#     glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
#     gluBuild2DMipmaps(GL_TEXTURE_2D, GL_RED, image.shape[1], image.shape[0],
#                       GL_RED, GL_UNSIGNED_BYTE, image)
#
#     return textureid


def create_grayscale_texture(image: NDArray[np.uint8]) -> int:
    image = np.array(image, dtype=np.uint8)
    gl.glActiveTexture(gl.GL_TEXTURE0)
    textureid = gl.glGenTextures(1)
    gl.glBindTexture(gl.GL_TEXTURE_2D, textureid)
    swizzle_mask = (gl.GL_RED, gl.GL_RED, gl.GL_RED, gl.GL_ONE)
    gl.glTexParameteriv(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_SWIZZLE_RGBA, swizzle_mask)

    gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_S, gl.GL_CLAMP_TO_BORDER)
    gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_T, gl.GL_CLAMP_TO_BORDER)
    gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
    gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR_MIPMAP_LINEAR)

    gl.glPixelStorei(gl.GL_UNPACK_ALIGNMENT, 1)
    gl.glPixelStorei(gl.GL_PACK_ALIGNMENT, 1)

    nLevels = int(np.floor(np.log2(max(image.shape))))

    gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_BASE_LEVEL, 0)
    gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAX_LEVEL, nLevels)

    gl.glTexImage2D(gl.GL_TEXTURE_2D, 0, gl.GL_RED, image.shape[1], image.shape[0],
                    0, gl.GL_RED, gl.GL_UNSIGNED_BYTE, image)

    gl.glGenerateMipmap(gl.GL_TEXTURE_2D)

    max_level = gl.glGetTexParameteriv(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAX_LEVEL)
    print(f"Maximum mipmap level: {max_level}")

    gl.glBindTexture(gl.GL_TEXTURE_2D, 0)

    return textureid


def create_rgba_texture(image: NDArray[np.uint8]) -> int:
    if np.issubdtype(image.dtype, np.uint8):
        image = image / 255.0
    elif isinstance(image.dtype, np.floating):
        pass
    else:
        raise NotImplementedError(f"Haven't thought about images with dtype {image.dtype} yet")

    gl.glActiveTexture(gl.GL_TEXTURE0)
    textureid = gl.glGenTextures(1)
    gl.glBindTexture(gl.GL_TEXTURE_2D, textureid)

    # swizzle_mask = (gl.GL_RED, gl.GL_RED, gl.GL_RGBA, gl.GL_ONE)
    # gl.glTexParameteriv(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_SWIZZLE_RGBA, swizzle_mask)

    gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_S, gl.GL_CLAMP_TO_BORDER)
    gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_T, gl.GL_CLAMP_TO_BORDER)
    gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
    gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR_MIPMAP_LINEAR)

    gl.glPixelStorei(gl.GL_PACK_ALIGNMENT, 1)
    gl.glPixelStorei(gl.GL_UNPACK_ALIGNMENT, 1)

    nLevels = int(np.floor(np.log2(max(image.shape))))
    gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_BASE_LEVEL, 0)
    gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAX_LEVEL, nLevels)

    gl.glTexImage2D(gl.GL_TEXTURE_2D, 0, gl.GL_RGBA, image.shape[1], image.shape[0],
                    0, gl.GL_RGBA, gl.GL_FLOAT, image)

    gl.glGenerateMipmap(gl.GL_TEXTURE_2D)

    max_level = gl.glGetTexParameteriv(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAX_LEVEL)
    print(f"Maximum mipmap level: {max_level}")

    gl.glBindTexture(gl.GL_TEXTURE_2D, 0)

    return textureid
