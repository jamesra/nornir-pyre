import logging
import sys
from dependency_injector import containers, providers
import wx
import yaml
import os
from typing import Generator

from pyre.commands.stos.rigidtransformactionmap import RigidTransformActionMap
from pyre.interfaces.managers import (ControlPointManagerKey, BufferType)
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
from pyre.observable.oset import ObservableSet
from pyre.container import IContainer
import pyre.commands.stos
from nornir_imageregistration.transforms.transform_type import TransformType
from pyre.commands.stos import GridTransformActionMap, TriangulationTransformActionMap


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

    # space = providers.Dependency(instance_of=pyre.Space)
    # view_type = providers.Dependency(instance_of=pyre.ui.ViewType)

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

    control_point_manager_key = providers.Factory(
        ControlPointManagerKey,
        transform_controller=transform_controller
    )
    # Returns the key for the configured transform controller and space
    controlpointmap_manager = providers.ThreadSafeSingleton(ControlPointMapManager)

    action_command_map = pyre.commands.container_overrides.action_command_dp_map
    # transform_control_point_action_maps: providers.Aggregate[providers.AbstractFactory[
    #        IControlPointActionMap]] = pyre.commands.container_overrides.transfom_control_point_action_maps

    # Friday PM to Monday Morning self:
    # You just figured out you could hand out a provider to a factory to get the dictionary provider to work
    transform_action_map = \
        providers.Dict({
            TransformType.GRID: providers.Factory(GridTransformActionMap).provider,
            TransformType.MESH: providers.Factory(TriangulationTransformActionMap).provider,
            TransformType.RBF: providers.Factory(TriangulationTransformActionMap).provider,
            TransformType.RIGID: providers.Factory(RigidTransformActionMap).provider,
        })

    selected_points = providers.Object(ObservableSet[int](initial_set=None, call_wrapper=wx.CallAfter))

    # stos_settings: providers.Resource = providers.Resource(load_settings)
