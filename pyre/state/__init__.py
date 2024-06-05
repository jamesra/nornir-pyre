import os
from .viewtype import ViewType
from .gl_context_manager import GLContextManager, IGLContextManager
from .transformcontroller_glbuffer_manager import BufferType, TransformControllerGLBufferManager, \
    ITransformControllerGLBufferManager, GLBufferCollection
from .image_viewmodel_manager import IImageViewModelManager, ImageViewModelManager

from .stos import StosState, StosWindowConfig
from .mosaic import MosaicState
from .events import *
from .window_manager import IWindowManager, WindowManager
from .image_manager import ImageManager, IImageManager
from .image_viewmodel_manager import ImageViewModelManager, IImageViewModelManager
from .gl_context_manager import GLContextManager, IGLContextManager

# The global gl_context_manager


currentStosConfig = None  # type: StosState
currentMosaicConfig = None  # type: MosaicState


def init():
    global currentStosConfig
    currentStosConfig = StosState()

    global currentMosaicConfig
    currentMosaicConfig = MosaicState()


def InitializeStateFromArguments(arg_values):
    global currentStosConfig

    if 'stosFullPath' in arg_values and arg_values.stosFullPath is not None:
        currentStosConfig.LoadStos(arg_values.stosFullPath)
    else:
        if 'WarpedImageFullPath' in arg_values and arg_values.WarpedImageFullPath is not None:
            currentStosConfig.LoadWarpedImage(arg_values.WarpedImageFullPath)
        if 'FixedImageFullPath' in arg_values and arg_values.FixedImageFullPath is not None:
            currentStosConfig.LoadFixedImage(arg_values.FixedImageFullPath)

    if 'mosaicFullPath' in arg_values and arg_values.mosaicFullPath is not None:
        tiles_path = os.path.dirname(arg_values.mosaicFullPath)
        if 'mosaicTilesFullPath' in arg_values and arg_values.mosaicTilesFullPath is not None:
            tiles_path = arg_values.mosaicTilesFullPath

        currentMosaicConfig.LoadMosaic(arg_values.mosaicFullPath, tiles_path)


def create_gl_objects():
    global transform_gl_viewmodel
    transform_gl_viewmodel = pyre.viewmodels.TransformGLViewModel(currentStosConfig.TransformController)
