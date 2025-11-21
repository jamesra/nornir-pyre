# Qt-based shader implementations
from pyre.gl_engine.shaders_qt.color_shader_qt import ColorShader
from pyre.gl_engine.shaders_qt.controlpointset_shader_qt import ControlPointSetShader
from pyre.gl_engine.shaders_qt.overlay_shader_qt import OverlayShader, OverlayType
from pyre.gl_engine.shaders_qt.pointset_shader_qt import PointSetShader
from pyre.gl_engine.shaders_qt.texture_shader_qt import TextureShader
from pyre.gl_engine.shaders_qt.transform_shader_qt import TransformShader
from pyre.gl_engine.helpers import raise_on_error

__initialized = False
__initialized_qt = False


def are_shaders_initialized() -> bool:
    """Check if shaders have been initialized"""
    return __initialized_qt


# Qt-based shader instances (these are the ones used in Qt port)
# For compatibility, also create aliases without _qt suffix
texture_shader_qt = TextureShader()  # type: TextureShader | None
color_shader_qt = ColorShader()  # type: ColorShader | None
transform_shader_qt = TransformShader()  # type: TransformShader | None
pointset_shader_qt = PointSetShader()  # type: PointSetShader | None
controlpointset_shader_qt = ControlPointSetShader()  # Type: ControlPointSetShader | None
overlay_shader_qt = OverlayShader()  # Type: OverlayShader | None


def InitializeShaders():
    """This must be called after the OpenGL Context is created.
    For Qt-based shaders, this initializes the Qt shader instances."""
    # Since this module is imported as shaders_qt, InitializeShaders should initialize Qt shaders
    InitializeShadersQt()


def InitializeShadersQt():
    """Initialize the Qt-based shader implementations. This must be called after the OpenGL Context is created"""
    global __initialized_qt
    global texture_shader_qt
    global color_shader_qt
    global transform_shader_qt
    global pointset_shader_qt
    global controlpointset_shader_qt
    global overlay_shader_qt

    if not __initialized_qt:
        color_shader_qt.initialize_gl_objects()
        texture_shader_qt.initialize_gl_objects()
        transform_shader_qt.initialize_gl_objects()
        pointset_shader_qt.initialize_gl_objects()
        controlpointset_shader_qt.initialize_gl_objects()
        overlay_shader_qt.initialize_gl_objects()
        # Check for errors after shader initialization - this will raise if there's an error

        raise_on_error("after InitializeShadersQt - checking for errors from shader initialization")
        __initialized_qt = True
