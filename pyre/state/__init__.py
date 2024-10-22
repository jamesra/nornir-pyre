import os

from dependency_injector.wiring import Provide, inject

from pyre.state.managers.image_manager import ImageManager
from pyre.state.managers.image_viewmodel_manager import ImageViewModelManager
from pyre.state.managers.transformcontroller_glbuffer_manager import TransformControllerGLBufferManager
from .events import *
from .imageloader import ImageLoader
from .managers import *
from .mosaic import MosaicState
from .stos import StosState, StosWindowConfig
from pyre.interfaces.viewtype import ViewType
from ..container import IContainer
import pyre.interfaces.managers

# The global gl_context_manager


currentStosConfig = None  # type: StosState
currentMosaicConfig = None  # type: MosaicState


def init():
    global currentStosConfig
    currentStosConfig = StosState()

    global currentMosaicConfig
    currentMosaicConfig = MosaicState()


@inject
def InitializeStateFromArguments(stos_transform_controller: TransformController,
                                 arg_values,
                                 image_loader: pyre.interfaces.managers.IImageLoader = Provide[
                                     IContainer.image_loader]):
    global currentStosConfig

    if 'stosFullPath' in arg_values and arg_values.stosFullPath is not None:
        transform = image_loader.load_stos(arg_values.stosFullPath)
        stos_transform_controller.TransformModel = transform
    else:
        if 'WarpedImageFullPath' in arg_values and arg_values.WarpedImageFullPath is not None:
            image_loader.load_image_into_manager(ViewType.Target, arg_values.WarpedImageFullPath)
        if 'FixedImageFullPath' in arg_values and arg_values.FixedImageFullPath is not None:
            image_loader.load_image_into_manager(ViewType.Source, arg_values.FixedImageFullPath)

    if 'mosaicFullPath' in arg_values and arg_values.mosaicFullPath is not None:
        tiles_path = os.path.dirname(arg_values.mosaicFullPath)
        if 'mosaicTilesFullPath' in arg_values and arg_values.mosaicTilesFullPath is not None:
            tiles_path = arg_values.mosaicTilesFullPath

        currentMosaicConfig.LoadMosaic(arg_values.mosaicFullPath, tiles_path)
