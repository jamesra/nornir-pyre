import nornir_imageregistration.transforms
import pyre.settings
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
from ..settings import ImageAndMaskPath

# The global gl_context_manager


currentStosConfig = None  # type: StosState
currentMosaicConfig = None  # type: MosaicState


def init():
    global currentStosConfig
    currentStosConfig = StosState()

    global currentMosaicConfig
    currentMosaicConfig = MosaicState()


@inject
def UpdateSettingsFromArguments(arg_values,
                                image_loader: pyre.settings.AppSettings = Provide[
                                    IContainer.image_loader],
                                settings: pyre.settings.AppSettings = Provide[IContainer.settings]):
    if 'stosFullPath' in arg_values and arg_values.stosFullPath is not None:
        settings.stos.stos_filename = arg_values.stosFullPath

    else:
        if 'SourceImageFullPath' in arg_values and arg_values.SourceImageFullPath is not None:
            settings.stos.source_image_filename = arg_values.SourceImageFullPath
            image_loader.load_image_into_manager(ViewType.Target, arg_values.WarpedImageFullPath)
        if 'TargetImageFullPath' in arg_values and arg_values.TargetImageFullPath is not None:
            settings.stos.target_image_filename = arg_values.TargetImageFullPath
            image_loader.load_image_into_manager(ViewType.Source, arg_values.FixedImageFullPath)

    # if 'mosaicFullPath' in arg_values and arg_values.mosaicFullPath is not None:
    #     tiles_path = os.path.dirname(arg_values.mosaicFullPath)
    #     if 'mosaicTilesFullPath' in arg_values and arg_values.mosaicTilesFullPath is not None:
    #         tiles_path = arg_values.mosaicTilesFullPath
    #
    #     currentMosaicConfig.LoadMosaic(arg_values.mosaicFullPath, tiles_path)


@inject
def InitializeStateFromSettings(stos_transform_controller: TransformController,
                                image_loader: pyre.settings.AppSettings = Provide[IContainer.image_loader],
                                settings: pyre.settings.AppSettings = Provide[IContainer.settings]):
    if settings.stos.stos_filename is not None:
        load_result = image_loader.load_stos(settings.stos.stos_filename)
        transform = nornir_imageregistration.transforms.LoadTransform(load_result.stos.Transform)
        stos_transform_controller.TransformModel = transform

        settings.stos.source_image = ImageAndMaskPath(image_fullpath=load_result.source.image_fullpath,
                                                      mask_fullpath=load_result.source.mask_fullpath)
        settings.stos.target_image = ImageAndMaskPath(image_fullpath=load_result.target.image_fullpath,
                                                      mask_fullpath=load_result.target.mask_fullpath)
    else:
        if settings.stos.target_image.image_fullpath is not None:
            image_loader.load_image_into_manager(ViewType.Target, settings.stos.target_image.image_fullpath,
                                                 mask_path=settings.stos.target_image.mask_fullpath)
        if settings.stos.source_image.image_fullpath is not None:
            image_loader.load_image_into_manager(ViewType.Source, settings.stos.source_image.image_fullpath,
                                                 mask_path=settings.stos.source_image.mask_fullpath)
