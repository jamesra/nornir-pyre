import os
from .interfaces import IImageManager, IImageViewModelManager
from .mousepositionhistorymanager import MousePositionHistoryManager, IMousePositionHistoryManager
from .action import Action
from .viewtype import ViewType
from .gl_context_manager import GLContextManager, IGLContextManager
from .transformcontroller_glbuffer_manager import BufferType, TransformControllerGLBufferManager, \
    ITransformControllerGLBufferManager, GLBufferCollection

from .viewtype import ViewType
from .stos import StosState, StosWindowConfig
from .imageloader import ImageLoader
from .mosaic import MosaicState
from .events import *
from .window_manager import IWindowManager, WindowManager
from .image_manager import ImageManager
from .gl_context_manager import GLContextManager, IGLContextManager
from .image_viewmodel_manager import ImageViewModelManager
from .roi_manager import RegionManager, IRegionManager, IRegion

# The global gl_context_manager


currentStosConfig = None  # type: StosState
currentMosaicConfig = None  # type: MosaicState


def init():
    global currentStosConfig
    currentStosConfig = StosState()

    global currentMosaicConfig
    currentMosaicConfig = MosaicState()


def InitializeStateFromArguments(image_loader: ImageLoader, arg_values):
    global currentStosConfig

    if 'stosFullPath' in arg_values and arg_values.stosFullPath is not None:
        image_loader.load_stos(arg_values.stosFullPath)
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
