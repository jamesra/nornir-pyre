from .color_shader import ColorShader
from .texture_shader import TextureShader
from .transform_shader import TransformShader
from .pointset_shader import PointSetShader
from .controlpointset_shader import ControlPointSetShader
from .overlay_shader import OverlayShader

__initialized = False
texture_shader = TextureShader()  # type: TextureShader | None
color_shader = ColorShader()  # type: ColorShader | None
transform_shader = TransformShader()  # type: TransformShader | None
pointset_shader = PointSetShader()  # type: PointSetShader | None
controlpointset_shader = ControlPointSetShader()  # Type: ControlPointSetShader | None
overlay_shader = OverlayShader()  # Type: OverlayShader | None


def InitializeShaders():
    """This must be called after the OpenGL Context is created"""
    global __initialized
    global texture_shader
    global color_shader
    global transform_shader
    global pointset_shader
    global controlpointset_shader

    if not __initialized:
        color_shader.initialize_gl_objects()
        texture_shader.initialize_gl_objects()
        transform_shader.initialize_gl_objects()
        pointset_shader.initialize_gl_objects()
        controlpointset_shader.initialize_gl_objects()
        overlay_shader.initialize_gl_objects()
        __initialized = True
