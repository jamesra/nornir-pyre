import nornir_imageregistration.transforms
import pyre.settings
import os

from dependency_injector.wiring import Provide, inject

from pyre.state.managers.image_manager import ImageManager
from pyre.state.managers.image_viewmodel_manager import ImageViewModelManager
from pyre.controllers import TransformController
from pyre.state.managers.transform_controller_glbuffer_manager import TransformControllerGLBufferManager
from .events import *
from .imageloader import ImageLoader
from .managers import *
from .mosaic import MosaicState
from .stos import StosState, StosWindowConfig
from pyre.interfaces.viewtype import ViewType
from ..container import IContainer
import pyre.interfaces.managers
from ..settings import ImageAndMaskPath
from pyre.stos_registration import resolve_warped_and_fixed_image_data, sync_stos_registration_roles

# The global gl_context_manager

# Module-level state; prefer get_current_stos_config/set_current_stos_config (and mosaic) for testability.
currentStosConfig: StosState | None = None
currentMosaicConfig: MosaicState | None = None


def get_current_stos_config() -> StosState | None:
    """Return the current STOS config. Use set_current_stos_config() in tests to inject a mock."""
    return currentStosConfig


def set_current_stos_config(config: StosState | None) -> None:
    """Set the current STOS config. Used by launcher and tests."""
    global currentStosConfig
    currentStosConfig = config


def get_current_mosaic_config() -> MosaicState | None:
    """Return the current mosaic config. Use set_current_mosaic_config() in tests to inject a mock."""
    return currentMosaicConfig


def set_current_mosaic_config(config: MosaicState | None) -> None:
    """Set the current mosaic config. Used by launcher and tests."""
    global currentMosaicConfig
    currentMosaicConfig = config


def init():
    global currentStosConfig
    # StosState requires DI (image_loader, etc.); use set_current_stos_config from launcher/tests.
    currentStosConfig = None

    global currentMosaicConfig
    currentMosaicConfig = MosaicState()  # type: ignore[call-arg, arg-type]


@inject
def UpdateSettingsFromArguments(arg_values,
                                image_loader: pyre.settings.AppSettings = Provide[
                                    IContainer.image_loader],
                                settings: pyre.settings.AppSettings = Provide[IContainer.settings]):
    import logging
    _log = logging.getLogger(__name__)

    if 'stosFullPath' in arg_values and arg_values.stosFullPath is not None:
        settings.stos.stos_filename = arg_values.stosFullPath
        _log.info("STOS argument provided: %s", arg_values.stosFullPath)

    else:
        _log.info("No STOS argument provided at startup")
        if 'SourceImageFullPath' in arg_values and arg_values.SourceImageFullPath is not None:
            settings.stos.source_image_filename = arg_values.SourceImageFullPath  # type: ignore[attr-defined]
            image_loader.load_image_into_manager(ViewType.Target, arg_values.WarpedImageFullPath)  # type: ignore[attr-defined]
        if 'TargetImageFullPath' in arg_values and arg_values.TargetImageFullPath is not None:
            settings.stos.target_image_filename = arg_values.TargetImageFullPath  # type: ignore[attr-defined]
            image_loader.load_image_into_manager(ViewType.Source, arg_values.FixedImageFullPath)  # type: ignore[attr-defined]

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
    """Load the saved STOS or individual images from settings.

    Raises:
        FileNotFoundError: If the saved STOS file path does not exist on disk.
        ValueError: If the STOS file exists but its transform cannot be parsed.
    """
    import logging
    _log = logging.getLogger(__name__)

    if settings.stos.stos_filename is not None:
        _log.info("Attempting to load STOS from settings: %s", settings.stos.stos_filename)
        try:
            # Let FileNotFoundError propagate — callers show a user-visible dialog.
            load_result = image_loader.load_stos(settings.stos.stos_filename)  # type: ignore[attr-defined]
        except FileNotFoundError as e:
            _log.error("STOS load failed (file not found): %s", settings.stos.stos_filename)
            raise
        except ValueError as e:
            _log.error("STOS load failed (invalid data or missing linked image): %s | %s",
                       settings.stos.stos_filename, e)
            raise
        try:
            transform = nornir_imageregistration.transforms.LoadTransform(load_result.stos.Transform)
        except Exception as e:
            _log.error("STOS transform parse failed for %s: %s", settings.stos.stos_filename, e)
            raise ValueError(
                f"Could not parse the transform in '{settings.stos.stos_filename}':\n{e}") from e
        stos_transform_controller.TransformModel = transform

        settings.stos.source_image = ImageAndMaskPath(image_fullpath=load_result.source.image_fullpath,
                                                      mask_fullpath=load_result.source.mask_fullpath)
        settings.stos.target_image = ImageAndMaskPath(image_fullpath=load_result.target.image_fullpath,
                                                      mask_fullpath=load_result.target.mask_fullpath)
        stos_config = get_current_stos_config()
        if stos_config is not None:
            warped, fixed = resolve_warped_and_fixed_image_data(
                image_loader._image_manager,  # type: ignore[attr-defined]
                ViewType.Source.value,
                ViewType.Target.value,
                stos_filename=settings.stos.stos_filename,
                settings_source_image_path=settings.stos.source_image.image_fullpath,
                settings_target_image_path=settings.stos.target_image.image_fullpath,
            )
            sync_stos_registration_roles(stos_config, warped, fixed)
    else:
        if settings.stos.target_image is not None and settings.stos.target_image.image_fullpath is not None:
            try:
                image_loader.load_image_into_manager(ViewType.Target, settings.stos.target_image.image_fullpath,  # type: ignore[attr-defined]
                                                     mask_path=settings.stos.target_image.mask_fullpath)
            except (FileNotFoundError, ValueError) as e:
                _log.warning("Saved target image not found — starting without it: %s", e)
        if settings.stos.source_image is not None and settings.stos.source_image.image_fullpath is not None:
            try:
                image_loader.load_image_into_manager(ViewType.Source, settings.stos.source_image.image_fullpath,  # type: ignore[attr-defined]
                                                     mask_path=settings.stos.source_image.mask_fullpath)
            except (FileNotFoundError, ValueError) as e:
                _log.warning("Saved source image not found — starting without it: %s", e)
        stos_config = get_current_stos_config()
        if stos_config is not None:
            warped, fixed = resolve_warped_and_fixed_image_data(
                image_loader._image_manager,  # type: ignore[attr-defined]
                ViewType.Source.value,
                ViewType.Target.value,
                stos_filename=settings.stos.stos_filename,
                settings_source_image_path=(
                    settings.stos.source_image.image_fullpath
                    if settings.stos.source_image is not None else None
                ),
                settings_target_image_path=(
                    settings.stos.target_image.image_fullpath
                    if settings.stos.target_image is not None else None
                ),
            )
            sync_stos_registration_roles(stos_config, warped, fixed)
