from .shader_base import BaseShader, VertexShader, FragmentShader
from .color_shader import ColorShader
from .texture_shader import TextureShader
from .transform_shader import TransformShader
from .pointset_shader import PointSetShader

__initialized = False
texture_shader = None  # type: TextureShader | None
color_shader = None  # type: ColorShader | None
transform_shader = None  # type: TransformShader | None
pointset_shader = None  # type: PointSetShader | None


def InitializeShaders():
    """This must be called after the OpenGL Context is created"""
    global __initialized
    global texture_shader
    global color_shader
    global transform_shader
    global pointset_shader

    if not __initialized:
        texture_shader = TextureShader()
        color_shader = ColorShader()
        transform_shader = TransformShader()
        pointset_shader = PointSetShader()
        __initialized = True
