import logging
import sys
from dependency_injector import containers, providers

from pyre.interfaces.managers import (ICommandHistory, IGLContextManager, IImageViewModelManager, IRegionMap,
                                      ITransformControllerGLBufferManager,
                                      IMousePositionHistoryManager,
                                      IImageManager, IRegionMap,
                                      IImageViewModelManager,
                                      IGLContextManager, BufferType)
from pyre.state.managers.gl_context_manager import GLContextManager
from pyre.state.managers.image_viewmodel_manager import ImageViewModelManager
from pyre.state.managers.mousepositionhistorymanager import MousePositionHistoryManager
from pyre.state.managers.region_manager import RegionMap
from pyre.state.managers.transformcontroller_glbuffer_manager import TransformControllerGLBufferManager
from pyre.state.managers.command_history import CommandHistory
from pyre.state.managers.image_manager import ImageManager
from pyre.state.managers.window_manager import WindowManager
from pyre.state.managers.controlpointmapmanager import ControlPointMapManager
from pyre.state.imageloader import ImageLoader
from pyre.state import TransformController
import pyre.gl_engine.shaders.controlpointset_shader

from pyre.container import IContainer, ControlPointActionCommandMapType
from pyre.interfaces.action import ControlPointAction
import pyre.commands
import pyre.commands.stos
from nornir_imageregistration.transforms.transform_type import TransformType
from pyre.commands import DefaultTransformCommand
from pyre.commands.stos import TranslateControlPointCommand


# from pyre.state.managers import (CommandHistory, GLContextManager, ImageManager, ImageViewModelManager,
#                                  MousePositionHistoryManager,
#                                  RegionManager, TransformControllerGLBufferManager)

@containers.override(IContainer)
class StosContainer(containers.DeclarativeContainer):
    """IoC container for the application components."""
    config = providers.Configuration()
    logger = providers.Resource(
        logging.basicConfig,
        level=logging.INFO,
        stream=sys.stdout,
    )

    history_manager = providers.ThreadSafeSingleton(CommandHistory)
    region_manager = providers.ThreadSafeSingleton(RegionMap)
    mouse_position_history = providers.ThreadSafeSingleton(MousePositionHistoryManager)
    command_history = providers.ThreadSafeSingleton(CommandHistory)
    image_manager = providers.ThreadSafeSingleton(ImageManager)
    transform_glbuffermanager = providers.ThreadSafeSingleton(
        TransformControllerGLBufferManager, buffer_layouts={
            BufferType.ControlPoint: pyre.gl_engine.shaders.controlpointset_shader.pointset_layout,
            BufferType.Selection: pyre.gl_engine.shaders.controlpointset_shader.texture_index_layout
        })
    imageviewmodel_manager = providers.ThreadSafeSingleton(ImageViewModelManager, )
    glcontext_manager = providers.ThreadSafeSingleton(GLContextManager)
    window_manager = providers.ThreadSafeSingleton(WindowManager)

    image_loader = providers.Factory(ImageLoader)
    transform_controller = providers.ThreadSafeSingleton(TransformController)

    controlpointmap_manager = providers.ThreadSafeSingleton(ControlPointMapManager)

    action_command_map = pyre.commands.container_overrides.action_command_dp_map
