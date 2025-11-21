# Qt-based OpenGL Shader Implementation

This directory contains two implementations of OpenGL shader handling:

1. The original implementation using direct OpenGL calls via PyOpenGL
2. A new implementation using Qt's OpenGL system (QOpenGLShader and QOpenGLShaderProgram)

## Purpose

The Qt-based implementation provides the same functionality as the original but uses Qt's OpenGL system instead of
direct OpenGL calls. This has several advantages:

- Better integration with Qt's OpenGL widgets
- Automatic resource management through Qt's object system
- Simplified shader compilation and linking
- Improved error handling
- Consistent with the Qt-based texture implementation in `textures_qt.py`

## Available Shaders

Both implementations provide the same set of shaders:

- `ColorShader` / `ColorShader` - Colors fragments with a constant color
- `ControlPointSetShader` / `ControlPointSetShader` - Renders a set of points with a texture centered on each point
- `OverlayShader` / `OverlayShader` - Displays two textures and overlays them with a blend function
- `PointSetShader` / `PointSetShader` - Renders a set of points with a texture centered on each point
- `TextureShader` / `TextureShader` - Renders a texture using vertex and index buffers
- `TransformShader` / `TransformShader` - Has a pair of vertices and textures for source/target space and can tween
  between them

## Usage

To use the Qt-based implementation, simply import the Qt-based shader classes instead of the original ones:

```python
# Original implementation
from pyre.gl_engine.shaders import TextureShader, InitializeShaders

# Qt-based implementation
from pyre.gl_engine.shaders import TextureShader, InitializeShadersQt
```

Or use the pre-initialized instances:

```python
# Original implementation
from pyre.gl_engine.shaders import texture_shader

# Qt-based implementation
from pyre.gl_engine.shaders import texture_shader_qt
```

Remember to call `InitializeShadersQt()` after the OpenGL context is created to initialize the Qt-based shader
instances.

## Implementation Details

The Qt-based implementation:

1. Uses QOpenGLShader for shader compilation
2. Uses QOpenGLShaderProgram for shader program linking and management
3. Provides better error handling with detailed error messages
4. Uses Qt's uniform setting methods for setting shader parameters
5. Automatically manages shader resources through Qt's object system

## Base Classes

The base classes for the shader implementations are:

- `shader_base.py` - Contains the base classes for the original implementation
- `shader_base_qt.py` - Contains the base classes for the Qt-based implementation

These base classes provide the foundation for all shader implementations in the project.