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

def _adjust_image_for_gl(image: NDArray[np.uint8]) -> NDArray:
    if np.issubdtype(image.dtype, np.uint8):
        return image / 255.0
    elif isinstance(image.dtype, np.floating):
        return image.astype(np.float32, copy=False)
    else:
        raise NotImplementedError(f"Haven't thought about images with dtype {image.dtype} yet")


def _configure_texture_sampler(mag_filter: int = gl.GL_NEAREST, target: int = gl.GL_TEXTURE_2D):
    """
    Configures the texture to display itself as a microscopy image
    :param mag_filter: GL_NEAREST or GL_LINEAR, use GL_NEAREST for image data to show user where resolution limit is when zooming
    :return:
    """

    gl.glTexParameteri(target, gl.GL_TEXTURE_WRAP_S, gl.GL_CLAMP_TO_BORDER)
    gl.glTexParameteri(target, gl.GL_TEXTURE_WRAP_T, gl.GL_CLAMP_TO_BORDER)
    gl.glTexParameteri(target, gl.GL_TEXTURE_MAG_FILTER, mag_filter)
    gl.glTexParameteri(target, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR_MIPMAP_LINEAR)


def _configure_mipmaps(image_shape: NDArray[np.integer] | tuple[int, int], target: int = gl.GL_TEXTURE_2D, ):
    num_levels = int(np.floor(np.log2(max(image_shape))))
    gl.glTexParameteri(target, gl.GL_TEXTURE_BASE_LEVEL, 0)
    gl.glTexParameteri(target, gl.GL_TEXTURE_MAX_LEVEL, num_levels)
    gl.glGenerateMipmap(target)

    max_level = gl.glGetTexParameteriv(target, gl.GL_TEXTURE_MAX_LEVEL)
    print(f"Maximum mipmap level: {max_level}")


def create_grayscale_texture(image: NDArray[np.uint8]) -> int:
    image = np.array(image, dtype=np.uint8)
    gl.glActiveTexture(gl.GL_TEXTURE0)
    textureid = gl.glGenTextures(1)
    gl.glBindTexture(gl.GL_TEXTURE_2D, textureid)
    swizzle_mask = (gl.GL_RED, gl.GL_RED, gl.GL_RED, gl.GL_ONE)
    gl.glTexParameteriv(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_SWIZZLE_RGBA, swizzle_mask)

    _configure_texture_sampler()

    gl.glTexImage2D(gl.GL_TEXTURE_2D, 0, gl.GL_RED, image.shape[1], image.shape[0],
                    0, gl.GL_RED, gl.GL_UNSIGNED_BYTE, image)

    _configure_mipmaps(image.shape)

    gl.glBindTexture(gl.GL_TEXTURE_2D, 0)

    return textureid


def create_rgba_texture(image: NDArray[np.uint8]) -> int:
    image = _adjust_image_for_gl(image)
    gl.glActiveTexture(gl.GL_TEXTURE0)
    textureid = gl.glGenTextures(1)
    gl.glBindTexture(gl.GL_TEXTURE_2D, textureid)

    # swizzle_mask = (gl.GL_RED, gl.GL_RED, gl.GL_RGBA, gl.GL_ONE)
    # gl.glTexParameteriv(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_SWIZZLE_RGBA, swizzle_mask)

    _configure_texture_sampler(gl.GL_LINEAR)

    gl.glTexImage2D(gl.GL_TEXTURE_2D, 0, gl.GL_RGBA, image.shape[1], image.shape[0],
                    0, gl.GL_RGBA, gl.GL_FLOAT, image)

    _configure_mipmaps(image.shape)

    gl.glBindTexture(gl.GL_TEXTURE_2D, 0)

    return textureid


def read_grayscale_texture(texture_id: int, width: int, height: int) -> NDArray[np.uint8]:
    """
    Read a texture from the GPU
    """
    # Bind the texture
    gl.glBindTexture(gl.GL_TEXTURE_2D, texture_id)

    # Allocate a numpy array to hold the texture data
    img_data = np.empty((width, height), dtype=np.uint8)

    # Read the texture data into the numpy array
    gl.glGetTexImage(gl.GL_TEXTURE_2D, 0, gl.GL_RED, gl.GL_UNSIGNED_BYTE, img_data)

    # Unbind the texture
    gl.glBindTexture(gl.GL_TEXTURE_2D, 0)

    return img_data


def read_rgba_texture(texture_id: int, width: int, height: int) -> NDArray[np.uint8]:
    """
    Read a texture from the GPU into a numpy array
    """

    # Bind the texture
    gl.glBindTexture(gl.GL_TEXTURE_2D, texture_id)

    # Allocate a numpy array to hold the texture data
    img_data = np.empty((width, height, 4), dtype=np.uint8)

    # Read the texture data into the numpy array
    gl.glGetTexImage(gl.GL_TEXTURE_2D, 0, gl.GL_RGBA, gl.GL_UNSIGNED_BYTE, img_data)

    # Unbind the texture
    gl.glBindTexture(gl.GL_TEXTURE_2D, 0)

    return img_data


def create_rgba_texture_array(images: NDArray[np.uint8]) -> int:
    """Given a 3D array of images, create a 2D texture array"""
    images = _adjust_image_for_gl(images)
    # gl.glActiveTexture(gl.GL_TEXTURE0)
    textureid = gl.glGenTextures(1)
    gl.glBindTexture(gl.GL_TEXTURE_2D_ARRAY, textureid)

    z_size, y_size, x_size, num_channels = images.shape
    layer_count = z_size
    images = images.astype(np.float32, copy=False)
    gl.glTexImage3D(gl.GL_TEXTURE_2D_ARRAY, 0, gl.GL_RGBA,
                    x_size, y_size, layer_count,
                    0, gl.GL_RGBA, gl.GL_FLOAT, None)

    # Loop through each texture and add it to the array
    for z in range(images.shape[0]):
        texture_data = images[z, :, :, :]
        # Copy the texture into the texture array
        gl.glTexSubImage3D(gl.GL_TEXTURE_2D_ARRAY,
                           0, 0, 0, z,
                           x_size, y_size, 1,
                           gl.GL_RGBA,
                           gl.GL_FLOAT,
                           texture_data)

    # swizzle_mask = (gl.GL_RED, gl.GL_RED, gl.GL_RGBA, gl.GL_ONE)
    # gl.glTexParameteriv(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_SWIZZLE_RGBA, swizzle_mask)

    _configure_texture_sampler(gl.GL_LINEAR, target=gl.GL_TEXTURE_2D_ARRAY)

    _configure_mipmaps((y_size, x_size), target=gl.GL_TEXTURE_2D_ARRAY)

    gl.glBindTexture(gl.GL_TEXTURE_2D, 0)

    return textureid
