import nornir_imageregistration.transforms
from nornir_imageregistration.files.stosfile import StosFile
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
from ..settings import ImageAndMaskPath, AppSettings
from pyre.stos_registration import (
    try_resolve_source_and_target_image_data,
    sync_stos_registration_roles,
    apply_stos_transform_to_controller,
    wire_stos_state_after_load,
)
from pyre.stos_manual_paths import resolve_stos_restore_path

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


def _clear_stale_stos_restore_settings(settings: AppSettings) -> None:
    """Drop persisted STOS paths so the next launch does not retry a dead restore."""
    import logging
    logging.getLogger(__name__).info("Clearing stale STOS restore paths from settings")
    settings.stos.stos_filename = None
    settings.stos.stos_dirname = None
    settings.stos.source_image = None
    settings.stos.target_image = None


def _sync_registration_roles_from_manager(
        stos_config: StosState,
        image_manager: ImageManager,
        *,
        stos_filename: str | None,
        stos: StosFile | None = None,
        settings_source_image_path: str | None,
        settings_target_image_path: str | None,
) -> None:
    """Update StosState source/target registration roles when both image slots are loaded."""
    resolved = try_resolve_source_and_target_image_data(
        image_manager,
        ViewType.Source.value,
        ViewType.Target.value,
        stos_filename=stos_filename,
        stos=stos,
        settings_source_image_path=settings_source_image_path,
        settings_target_image_path=settings_target_image_path,
    )
    if resolved is not None:
        warped, fixed = resolved
        sync_stos_registration_roles(stos_config, warped, fixed)


@inject
def UpdateSettingsFromArguments(arg_values,
                                image_loader: ImageLoader = Provide[IContainer.image_loader],
                                settings: AppSettings = Provide[IContainer.settings]):
    import logging
    _log = logging.getLogger(__name__)

    if 'stosFullPath' in arg_values and arg_values.stosFullPath is not None:
        settings.stos.stos_filename = arg_values.stosFullPath
        _log.info("STOS argument provided: %s", arg_values.stosFullPath)

    else:
        _log.info("No STOS argument provided at startup")
        if arg_values.TargetImageFullPath is not None:
            result = image_loader.load_image_into_manager(
                key=ViewType.Target.value,
                image_fullpath=arg_values.TargetImageFullPath,
                mask_fullpath=None,
            )
            image_loader.create_image_viewmodel(load_result=result)
            settings.stos.target_image = ImageAndMaskPath(
                image_fullpath=result.image_fullpath,
                mask_fullpath=result.mask_fullpath,
            )
        if arg_values.SourceImageFullPath is not None:
            result = image_loader.load_image_into_manager(
                key=ViewType.Source.value,
                image_fullpath=arg_values.SourceImageFullPath,
                mask_fullpath=None,
            )
            image_loader.create_image_viewmodel(load_result=result)
            settings.stos.source_image = ImageAndMaskPath(
                image_fullpath=result.image_fullpath,
                mask_fullpath=result.mask_fullpath,
            )

    # if 'mosaicFullPath' in arg_values and arg_values.mosaicFullPath is not None:
    #     tiles_path = os.path.dirname(arg_values.mosaicFullPath)
    #     if 'mosaicTilesFullPath' in arg_values and arg_values.mosaicTilesFullPath is not None:
    #         tiles_path = arg_values.mosaicTilesFullPath
    #
    #     currentMosaicConfig.LoadMosaic(arg_values.mosaicFullPath, tiles_path)


@inject
def InitializeStateFromSettings(stos_transform_controller: TransformController,
                                image_loader: ImageLoader = Provide[IContainer.image_loader],
                                settings: AppSettings = Provide[IContainer.settings]):
    """Load the saved STOS or individual images from settings.

    Raises:
        FileNotFoundError: If the saved STOS file path does not exist on disk.
        ValueError: If the STOS file exists but its transform cannot be parsed.
    """
    import logging
    _log = logging.getLogger(__name__)
    image_manager: ImageManager = image_loader._image_manager  # type: ignore[attr-defined]

    if settings.stos.stos_filename is not None:
        restore_path = resolve_stos_restore_path(
            settings.stos.stos_filename,
            stos_group_folder=settings.stos.stos_opened_from_browser_folder,
            stos_browser_basename=settings.stos.stos_browser_basename,
            stos_file_source=settings.stos.stos_file_source,
            flat_manual=settings.stos.stos_browser_flat_manual,
        )
        _log.info("Attempting to load STOS from settings: %s (resolved: %s)",
                  settings.stos.stos_filename, restore_path)
        try:
            load_result = image_loader.load_stos(restore_path)
        except FileNotFoundError:
            _log.error("STOS load failed (file not found): %s", restore_path)
            _clear_stale_stos_restore_settings(settings)
            raise
        except ValueError as e:
            _log.error("STOS load failed (invalid data or missing linked image): %s | %s",
                       restore_path, e)
            _clear_stale_stos_restore_settings(settings)
            raise
        image_loader.create_image_viewmodel(load_result=load_result.source)
        image_loader.create_image_viewmodel(load_result=load_result.target)
        try:
            apply_stos_transform_to_controller(stos_transform_controller, load_result.stos.Transform)  # type: ignore[arg-type]
        except Exception as e:
            _log.error("STOS transform parse failed for %s: %s", restore_path, e)
            _clear_stale_stos_restore_settings(settings)
            raise ValueError(
                f"Could not parse the transform in '{restore_path}':\n{e}") from e
        settings.stos.stos_filename = restore_path

        settings.stos.source_image = ImageAndMaskPath(image_fullpath=load_result.source.image_fullpath,
                                                      mask_fullpath=load_result.source.mask_fullpath)
        settings.stos.target_image = ImageAndMaskPath(image_fullpath=load_result.target.image_fullpath,
                                                      mask_fullpath=load_result.target.mask_fullpath)
        stos_config = get_current_stos_config()
        if stos_config is not None:
            wire_stos_state_after_load(stos_config, image_loader._image_viewmodel_manager)  # type: ignore[attr-defined]
            _sync_registration_roles_from_manager(
                stos_config,
                image_manager,
                stos_filename=restore_path,
                stos=load_result.stos,
                settings_source_image_path=settings.stos.source_image.image_fullpath,
                settings_target_image_path=settings.stos.target_image.image_fullpath,
            )
    else:
        if settings.stos.target_image is not None and settings.stos.target_image.image_fullpath is not None:
            try:
                result = image_loader.load_image_into_manager(
                    key=ViewType.Target.value,
                    image_fullpath=settings.stos.target_image.image_fullpath,
                    mask_fullpath=settings.stos.target_image.mask_fullpath,
                )
                image_loader.create_image_viewmodel(load_result=result)
            except (FileNotFoundError, ValueError) as e:
                _log.warning("Saved target image not found — starting without it: %s", e)
        if settings.stos.source_image is not None and settings.stos.source_image.image_fullpath is not None:
            try:
                result = image_loader.load_image_into_manager(
                    key=ViewType.Source.value,
                    image_fullpath=settings.stos.source_image.image_fullpath,
                    mask_fullpath=settings.stos.source_image.mask_fullpath,
                )
                image_loader.create_image_viewmodel(load_result=result)
            except (FileNotFoundError, ValueError) as e:
                _log.warning("Saved source image not found — starting without it: %s", e)
        stos_config = get_current_stos_config()
        if stos_config is not None:
            _sync_registration_roles_from_manager(
                stos_config,
                image_manager,
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
