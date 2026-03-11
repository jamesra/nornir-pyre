import ctypes
import numpy as np
from numpy.typing import NDArray
from PyQt6.QtGui import QImage, QColor, QOpenGLContext
from PyQt6.QtOpenGL import QOpenGLTexture
import OpenGL.GL as gl
from pyre.gl_engine.helpers import raise_on_error, check_for_error

import nornir_imageregistration


def _numpy_to_qimage(image: NDArray[np.uint8]) -> QImage:
    """
    Convert a numpy array to a QImage using efficient bulk operations.

    Args:
        image: A numpy array containing image data

    Returns:
        A QImage representing the same image data
    """
    if len(image.shape) == 2:  # Grayscale image
        height, width = image.shape
        # Ensure array is contiguous and in the right format
        if not image.flags['C_CONTIGUOUS']:
            image = np.ascontiguousarray(image)

        # Create QImage directly from bytes - much faster than pixel-by-pixel
        qimage = QImage(image.data, width, height, width, QImage.Format.Format_Grayscale8)
        # Make a copy to ensure data persists beyond the numpy array lifetime
        return qimage.copy()

    elif len(image.shape) == 3 and image.shape[2] == 4:  # RGBA image
        height, width, _ = image.shape
        # Ensure array is contiguous and in the right format
        if not image.flags['C_CONTIGUOUS']:
            image = np.ascontiguousarray(image)

        # Create QImage directly from bytes - much faster than pixel-by-pixel
        # RGBA8888 format expects bytes in R,G,B,A order per pixel
        qimage = QImage(image.data, width, height, width * 4, QImage.Format.Format_RGBA8888)
        # Make a copy to ensure data persists beyond the numpy array lifetime
        return qimage.copy()
    else:
        raise ValueError(f"Unsupported image shape: {image.shape}")


def _qimage_to_numpy(qimage: QImage) -> NDArray[np.uint8]:
    """
    Convert a QImage to a numpy array using efficient bulk operations.

    Args:
        qimage: A QImage object

    Returns:
        A numpy array containing the image data
    """
    width = qimage.width()
    height = qimage.height()

    if qimage.format() == QImage.Format.Format_Grayscale8:
        # Convert to bytes and create numpy array directly - much faster
        # In PyQt6, constBits() returns a sip.voidptr, convert via ctypes
        import ctypes
        bits = qimage.constBits()
        if not bits:
            raise RuntimeError("Failed to get QImage bits")

        # Use bytesPerLine() to get the actual stride (may be padded)
        bytes_per_line = qimage.bytesPerLine()
        total_bytes = bytes_per_line * height
        # Get the raw bytes from the voidptr
        bytes_data = ctypes.string_at(bits, total_bytes)

        # Create array - handle padding if present
        if bytes_per_line == width:
            # No padding, direct reshape (common case - fastest path)
            result = np.frombuffer(bytes_data, dtype=np.uint8).reshape((height, width))
        else:
            # Has padding, need to copy row by row (uncommon case)
            result = np.zeros((height, width), dtype=np.uint8)
            for y in range(height):
                start = y * bytes_per_line
                result[y, :] = np.frombuffer(bytes_data[start:start + width], dtype=np.uint8)
        return result.copy()  # Make a copy to ensure data persists

    elif qimage.format() == QImage.Format.Format_RGBA8888:
        # Convert to bytes and create numpy array directly - much faster
        import ctypes
        bits = qimage.constBits()
        if not bits:
            raise RuntimeError("Failed to get QImage bits")

        # Use bytesPerLine() to get the actual stride (may be padded)
        bytes_per_line = qimage.bytesPerLine()
        expected_bytes_per_line = width * 4
        total_bytes = bytes_per_line * height
        # Get the raw bytes from the voidptr
        bytes_data = ctypes.string_at(bits, total_bytes)

        # Create array - handle padding if present
        if bytes_per_line == expected_bytes_per_line:
            # No padding, direct reshape (common case - fastest path)
            result = np.frombuffer(bytes_data, dtype=np.uint8).reshape((height, width, 4))
        else:
            # Has padding, need to copy row by row (uncommon case)
            result = np.zeros((height, width, 4), dtype=np.uint8)
            for y in range(height):
                start = y * bytes_per_line
                end = start + expected_bytes_per_line
                result[y, :, :] = np.frombuffer(bytes_data[start:end], dtype=np.uint8).reshape((width, 4))
        return result.copy()  # Make a copy to ensure data persists
    else:
        raise ValueError(f"Unsupported QImage format: {qimage.format()}")


def _configure_texture(texture: QOpenGLTexture, mag_filter: gl.GLint = gl.GL_NEAREST):
    """
    Configure a QOpenGLTexture with appropriate parameters for microscopy images.
    
    This must be called BEFORE allocateStorage() to avoid errors.

    Args:
        texture: The QOpenGLTexture to configure
        mag_filter: The magnification filter to use (GL_NEAREST or GL_LINEAR)

    Returns:
        None
    """
    # Set wrap mode
    texture.setWrapMode(QOpenGLTexture.WrapMode.ClampToBorder)

    # Set magnification filter
    if mag_filter == gl.GL_NEAREST:
        texture.setMagnificationFilter(QOpenGLTexture.Filter.Nearest)
    else:
        texture.setMagnificationFilter(QOpenGLTexture.Filter.Linear)

    # Set minification filter - use LinearMipMapLinear for better quality when zoomed out
    texture.setMinificationFilter(QOpenGLTexture.Filter.LinearMipMapLinear)

    # Enable auto mipmap generation - this must be set before allocateStorage()
    # Qt will generate mipmaps automatically when setData() is called
    texture.setAutoMipMapGenerationEnabled(True)


def create_grayscale_texture(image: NDArray[np.uint8]) -> int:
    """
    Create a grayscale texture from a numpy array using PyOpenGL calls.

    Args:
        image: A numpy array containing grayscale image data

    Returns:
        The OpenGL texture ID
    """

    # Ensure we have a valid OpenGL context before creating textures
    current_context = QOpenGLContext.currentContext()
    if current_context is None or not current_context.isValid():
        raise RuntimeError(
            "Cannot create texture: No valid OpenGL context is current. "
            "Textures must be created when an OpenGL context is active."
        )

    image = nornir_imageregistration.image_to_uint8(image)
    
    # Ensure array is contiguous
    if not image.flags['C_CONTIGUOUS']:
        image = np.ascontiguousarray(image)
    
    height, width = image.shape

    # Generate and bind texture using PyOpenGL
    gl.glActiveTexture(gl.GL_TEXTURE0)
    raise_on_error("after glActiveTexture in create_grayscale_texture")
    
    texture_id = gl.glGenTextures(1)
    raise_on_error("after glGenTextures in create_grayscale_texture")
    
    gl.glBindTexture(gl.GL_TEXTURE_2D, texture_id)
    raise_on_error("after glBindTexture in create_grayscale_texture")

    # Set swizzle mask to make it appear as grayscale
    swizzle_mask = (gl.GL_RED, gl.GL_RED, gl.GL_RED, gl.GL_ONE)
    gl.glTexParameteriv(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_SWIZZLE_RGBA, swizzle_mask)
    raise_on_error("after glTexParameteriv (swizzle) in create_grayscale_texture")

    # Configure texture parameters
    gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_S, gl.GL_CLAMP_TO_BORDER)
    gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_T, gl.GL_CLAMP_TO_BORDER)
    # Explicit border (0,0,0,1) so out-of-bounds samples are black; avoids bright dot artifacts
    # when UVs or LOD sampling touch the border (undefined border is driver-dependent).
    border_color = np.array([0.0, 0.0, 0.0, 1.0], dtype=np.float32)
    gl.glTexParameterfv(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_BORDER_COLOR, border_color)
    gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_NEAREST)
    gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR_MIPMAP_LINEAR)
    raise_on_error("after texture parameter configuration in create_grayscale_texture")

    # Explicit row length and alignment avoid top-left pixel artifact (driver stride assumptions).
    gl.glPixelStorei(gl.GL_UNPACK_ROW_LENGTH, width)
    gl.glPixelStorei(gl.GL_UNPACK_ALIGNMENT, 1)
    # Upload texture data using glTexImage2D - this accepts numpy arrays directly
    gl.glTexImage2D(gl.GL_TEXTURE_2D, 0, gl.GL_RED, width, height,
                    0, gl.GL_RED, gl.GL_UNSIGNED_BYTE, image)
    gl.glPixelStorei(gl.GL_UNPACK_ROW_LENGTH, 0)
    gl.glPixelStorei(gl.GL_UNPACK_ALIGNMENT, 4)
    raise_on_error("after glTexImage2D in create_grayscale_texture")

    # Configure and generate mipmaps
    max_dimension = max(width, height)
    if max_dimension > 0:
        num_mip_levels = int(np.floor(np.log2(max_dimension)))
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_BASE_LEVEL, 0)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAX_LEVEL, num_mip_levels)
        raise_on_error("after mipmap level configuration in create_grayscale_texture")
    
    gl.glGenerateMipmap(gl.GL_TEXTURE_2D)
    raise_on_error("after glGenerateMipmap in create_grayscale_texture")

    # Unbind texture
    gl.glBindTexture(gl.GL_TEXTURE_2D, 0)
    raise_on_error("after unbinding texture in create_grayscale_texture")

    # Note: No need to store texture object - PyOpenGL uses raw texture IDs
    return texture_id


def create_rgba_texture(image: NDArray[np.uint8]) -> int:
    """
    Create an RGBA texture from a numpy array using PyOpenGL calls.

    Args:
        image: A numpy array containing RGBA image data

    Returns:
        The OpenGL texture ID
    """
    # Ensure we have a valid OpenGL context before creating textures
    current_context = QOpenGLContext.currentContext()
    if current_context is None or not current_context.isValid():
        raise RuntimeError(
            "Cannot create texture: No valid OpenGL context is current. "
            "Textures must be created when an OpenGL context is active."
        )

    # Convert to uint8 if needed
    if np.issubdtype(image.dtype, np.floating):
        image = (image * 255).astype(np.uint8)

    # Ensure array is contiguous
    if not image.flags['C_CONTIGUOUS']:
        image = np.ascontiguousarray(image)
    
    height, width, _ = image.shape

    # Generate and bind texture using PyOpenGL
    gl.glActiveTexture(gl.GL_TEXTURE0)
    raise_on_error("after glActiveTexture in create_rgba_texture")
    
    texture_id = gl.glGenTextures(1)
    raise_on_error("after glGenTextures in create_rgba_texture")
    
    gl.glBindTexture(gl.GL_TEXTURE_2D, texture_id)
    raise_on_error("after glBindTexture in create_rgba_texture")

    # Configure texture parameters
    gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_S, gl.GL_CLAMP_TO_BORDER)
    gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_T, gl.GL_CLAMP_TO_BORDER)
    gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
    gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR_MIPMAP_LINEAR)
    raise_on_error("after texture parameter configuration in create_rgba_texture")

    # Explicit row length and alignment avoid top-left pixel artifact (driver stride assumptions).
    gl.glPixelStorei(gl.GL_UNPACK_ROW_LENGTH, width)
    gl.glPixelStorei(gl.GL_UNPACK_ALIGNMENT, 1)
    # Upload texture data using glTexImage2D - this accepts numpy arrays directly
    gl.glTexImage2D(gl.GL_TEXTURE_2D, 0, gl.GL_RGBA, width, height,
                    0, gl.GL_RGBA, gl.GL_UNSIGNED_BYTE, image)
    gl.glPixelStorei(gl.GL_UNPACK_ROW_LENGTH, 0)
    gl.glPixelStorei(gl.GL_UNPACK_ALIGNMENT, 4)
    raise_on_error("after glTexImage2D in create_rgba_texture")

    # Configure and generate mipmaps
    max_dimension = max(width, height)
    if max_dimension > 0:
        num_mip_levels = int(np.floor(np.log2(max_dimension)))
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_BASE_LEVEL, 0)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAX_LEVEL, num_mip_levels)
        raise_on_error("after mipmap level configuration in create_rgba_texture")
    
    gl.glGenerateMipmap(gl.GL_TEXTURE_2D)
    raise_on_error("after glGenerateMipmap in create_rgba_texture")

    # Unbind texture
    gl.glBindTexture(gl.GL_TEXTURE_2D, 0)
    raise_on_error("after unbinding texture in create_rgba_texture")

    # Note: No need to store texture object - PyOpenGL uses raw texture IDs
    return texture_id


def read_grayscale_texture(texture_id: int, width: int, height: int) -> NDArray[np.uint8]:
    """
    Read a grayscale texture from the GPU using PyOpenGL calls.

    Args:
        texture_id: The OpenGL texture ID
        width: The width of the texture
        height: The height of the texture

    Returns:
        A numpy array containing the texture data
    """
    # Ensure we have a valid OpenGL context
    current_context = QOpenGLContext.currentContext()
    if current_context is None or not current_context.isValid():
        raise RuntimeError("No valid OpenGL context is current")

    # Bind the texture using PyOpenGL
    gl.glBindTexture(gl.GL_TEXTURE_2D, texture_id)
    raise_on_error("after glBindTexture in read_grayscale_texture")

    # Create a numpy array to hold the texture data
    img_data = np.empty((height, width), dtype=np.uint8)

    # Read the texture data into the numpy array
    gl.glGetTexImage(gl.GL_TEXTURE_2D, 0, gl.GL_RED, gl.GL_UNSIGNED_BYTE, img_data)
    raise_on_error("after glGetTexImage in read_grayscale_texture")

    # Unbind the texture
    gl.glBindTexture(gl.GL_TEXTURE_2D, 0)
    raise_on_error("after unbinding texture in read_grayscale_texture")

    return img_data


def read_rgba_texture(texture_id: int, width: int, height: int) -> NDArray[np.uint8]:
    """
    Read an RGBA texture from the GPU using PyOpenGL calls.

    Args:
        texture_id: The OpenGL texture ID
        width: The width of the texture
        height: The height of the texture

    Returns:
        A numpy array containing the texture data
    """
    # Ensure we have a valid OpenGL context
    current_context = QOpenGLContext.currentContext()
    if current_context is None or not current_context.isValid():
        raise RuntimeError("No valid OpenGL context is current")

    # Bind the texture using PyOpenGL
    gl.glBindTexture(gl.GL_TEXTURE_2D, texture_id)
    raise_on_error("after glBindTexture in read_rgba_texture")

    # Create a numpy array to hold the texture data
    img_data = np.empty((height, width, 4), dtype=np.uint8)

    # Read the texture data into the numpy array
    gl.glGetTexImage(gl.GL_TEXTURE_2D, 0, gl.GL_RGBA, gl.GL_UNSIGNED_BYTE, img_data)
    raise_on_error("after glGetTexImage in read_rgba_texture")

    # Unbind the texture
    gl.glBindTexture(gl.GL_TEXTURE_2D, 0)
    raise_on_error("after unbinding texture in read_rgba_texture")

    return img_data


def create_rgba_texture_array(images: NDArray[np.uint8]) -> int:
    """
    Create a 2D texture array from a 3D array of images.

    Args:
        images: A 3D numpy array containing multiple RGBA images

    Returns:
        The OpenGL texture ID
    """
    # Convert to uint8 if needed
    if np.issubdtype(images.dtype, np.floating):
        images = (images * 255).astype(np.uint8)

    z_size, y_size, x_size, num_channels = images.shape

    # Create and configure the texture
    texture = QOpenGLTexture(QOpenGLTexture.Target.Target2DArray)

    # Set format, size, and layers BEFORE configuring parameters
    # This ensures the texture knows its dimensions for mipmap generation
    texture.setFormat(QOpenGLTexture.TextureFormat.RGBA8_UNorm)
    texture.setSize(x_size, y_size)
    texture.setLayers(z_size)  # Set the number of layers explicitly

    # Configure the texture parameters before allocating storage
    _configure_texture(texture, gl.GL_LINEAR)

    # Allocate storage
    texture.allocateStorage()

    texture_id = texture.textureId()
    gl.glBindTexture(gl.GL_TEXTURE_2D_ARRAY, texture_id)
    try:
        # Upload each layer with raw glTexSubImage3D so GL_UNPACK_* is respected
        # (Qt's setData can ignore it, causing first-texel artifact = grid of dots on control points).
        for z in range(z_size):
            image_slice = images[z]
            if not image_slice.flags['C_CONTIGUOUS']:
                image_slice = np.ascontiguousarray(image_slice)
            gl.glPixelStorei(gl.GL_UNPACK_ROW_LENGTH, x_size)
            gl.glPixelStorei(gl.GL_UNPACK_ALIGNMENT, 1)
            try:
                data_ptr = image_slice.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8))
                gl.glTexSubImage3D(
                    gl.GL_TEXTURE_2D_ARRAY, 0,
                    0, 0, z,
                    x_size, y_size, 1,
                    gl.GL_RGBA, gl.GL_UNSIGNED_BYTE,
                    data_ptr
                )
            finally:
                gl.glPixelStorei(gl.GL_UNPACK_ROW_LENGTH, 0)
                gl.glPixelStorei(gl.GL_UNPACK_ALIGNMENT, 4)
    finally:
        gl.glBindTexture(gl.GL_TEXTURE_2D_ARRAY, 0)

    # Store the texture object in a global dictionary to prevent it from being garbage collected
    if not hasattr(create_rgba_texture_array, "_textures"):
        create_rgba_texture_array._textures = {}
    create_rgba_texture_array._textures[texture_id] = texture

    return texture_id


def get_texture_array_length(texture_id: int) -> int:
    """
    Get the number of layers in a texture array.

    Args:
        texture_id: The OpenGL texture ID

    Returns:
        The number of layers in the texture array
    """
    # Get the texture object from the global dictionary
    if not hasattr(create_rgba_texture_array, "_textures") or texture_id not in create_rgba_texture_array._textures:
        raise ValueError(f"Texture ID {texture_id} not found")

    texture = create_rgba_texture_array._textures[texture_id]

    # Return the depth of the texture array
    return texture.depth()
