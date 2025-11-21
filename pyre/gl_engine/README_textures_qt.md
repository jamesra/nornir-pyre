# Qt-based OpenGL Texture Implementation

This directory contains two implementations of OpenGL texture handling:

1. `textures.py` - The original implementation using direct OpenGL calls via PyOpenGL
2. `textures_qt.py` - A new implementation using Qt's OpenGL system (QImage and QOpenGLTexture)

## Purpose

The Qt-based implementation (`textures_qt.py`) provides the same functionality as the original but uses Qt's OpenGL
system instead of direct OpenGL calls. This has several advantages:

- Better integration with Qt's OpenGL widgets
- Automatic resource management through Qt's object system
- Simplified texture creation and manipulation
- Improved context handling

## API

Both implementations provide the same API:

- `create_grayscale_texture(image)` - Creates a grayscale texture from a numpy array
- `create_rgba_texture(image)` - Creates an RGBA texture from a numpy array
- `read_grayscale_texture(texture_id, width, height)` - Reads a grayscale texture from the GPU
- `read_rgba_texture(texture_id, width, height)` - Reads an RGBA texture from the GPU
- `create_rgba_texture_array(images)` - Creates a 2D texture array from a 3D array of images
- `get_texture_array_length(texture_id)` - Gets the number of layers in a texture array

## Usage

To use the Qt-based implementation, simply import from `textures_qt` instead of `textures`:

```python
# Original implementation
from pyre.gl_engine import textures_gl

# Qt-based implementation
from pyre.gl_engine import textures_qt
```

## Implementation Details

The Qt-based implementation:

1. Converts numpy arrays to QImage objects
2. Uses QOpenGLTexture for texture creation and management
3. Stores texture objects in dictionaries to prevent garbage collection
4. Provides the same interface as the original implementation

## Testing

A test script (`test_textures_qt.py`) is provided to verify that both implementations produce the same results. Run it
with:

```python
python - m
pyre.gl_engine.test_textures_qt
```

## Conversion between numpy arrays and QImage

The Qt-based implementation includes helper functions for converting between numpy arrays and QImage objects:

- `_numpy_to_qimage(image)` - Converts a numpy array to a QImage
- `_qimage_to_numpy(qimage)` - Converts a QImage to a numpy array

These functions handle both grayscale and RGBA images.