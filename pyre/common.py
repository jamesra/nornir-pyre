'''
Created on Oct 16, 2012

@author: u0490822
'''
import logging
import tempfile
import copy
from typing import Iterable

logger = logging.getLogger(__name__)

from dependency_injector.wiring import Provide, inject
import numpy
from numpy.typing import NDArray
from PyQt6.QtWidgets import QWidget

import nornir_imageregistration
from nornir_imageregistration import ITransform, PointLike, AreaLike, ImageStats
from nornir_imageregistration.settings import StosBruteSettings, GridRefinement, SliceToSliceMethod
from nornir_imageregistration.transforms import IControlPoints
from nornir_imageregistration.transforms import utils as transform_utils
import nornir_imageregistration.assemble as assemble
import nornir_imageregistration.stos_brute as stos
import nornir_pools
import pyre
from pyre.container import IContainer
from pyre.interfaces.managers import IImageManager, IWindowManager
from pyre.interfaces.managers.command_history import ICommandHistory
from pyre.interfaces.viewtype import ViewType
from pyre.controllers.transformcontroller import TransformController
from pyre.settings import AppSettings
from pyre.stos_registration import normalize_rigid_transform_for_pyre_editing, resolve_warped_and_fixed_image_data


def SaveRegisteredWarpedImage(fileFullPath: str, transform: ITransform, warpedImage: NDArray):
    """Save the warped image registered into fixed space to a file. Uses current STOS config for fixed shape."""
    config = pyre.state.get_current_stos_config()
    if config is None:
        raise RuntimeError("No current STOS config")
    assert config.FixedImageViewModel is not None and config.WarpedImageViewModel is not None  # type: ignore[attr-defined]
    registeredImage = AssembleHugeRegisteredWarpedImage(transform,
                                                        config.FixedImageViewModel.Image.shape,  # type: ignore[arg-type, attr-defined]
                                                        config.WarpedImageViewModel.Image)  # type: ignore[attr-defined]

    nornir_imageregistration.SaveImage(fileFullPath, registeredImage)


def AssembleHugeRegisteredWarpedImage(transform: ITransform, fixedImageShape: NDArray,
                                      warpedImage: NDArray):
    """Apply transform to warped image and assemble into fixed space. Cuts image into tiles for large data."""
    return assemble.TransformImage(transform, fixedImageShape, warpedImage, CropUndefined=False)


def _apply_lookat_to_window(window, lookat, scale: float):
    """Set a window's camera to the given lookat point and scale."""
    window.imagepanel.camera.x = lookat[0]
    window.imagepanel.camera.y = lookat[1]
    window.imagepanel.camera.scale = scale


def SyncWindows(LookAt, scale: float, window_manager: IWindowManager) -> None:
    """Make all windows look at the same spot with the same magnification; LookAt is in fixed space.

    ``window_manager`` must register ViewType Source, Target, and Composite (the STOS layout).
    """
    if not (
        ViewType.Composite in window_manager
        and ViewType.Source in window_manager
        and ViewType.Target in window_manager
    ):
        raise ValueError("window_manager must register Source, Target, and Composite views")
    composite_win = window_manager[ViewType.Composite]
    source_win = window_manager[ViewType.Source]
    target_win = window_manager[ViewType.Target]
    for win in (composite_win, source_win, target_win):
        _apply_lookat_to_window(win, LookAt, scale)
    if target_win.isVisible():
        config = pyre.state.get_current_stos_config()
        if config is not None and config._TransformViewModel is not None:
            config._TransformViewModel.InverseTransform([LookAt])


def sync_stos_windows(LookAt, scale: float) -> None:
    """Sync cameras using the current :class:`pyre.state.StosState` window manager."""
    config = pyre.state.get_current_stos_config()
    if config is None or config.window_manager is None:
        raise RuntimeError("No STOS config with window_manager; cannot sync windows")
    SyncWindows(LookAt, scale, config.window_manager)


def repaint_peer_stos_gl_panels(
        window_manager: IWindowManager,
        exclude_gl_panel: QWidget | None = None) -> None:
    """Synchronously repaint visible STOS GL panels except the one driving the drag.

    QOpenGLWidget.update() on peer windows is often deferred until mouse release
    while another STOS panel holds the grab during translate drags.
    """
    from pyre.ui.windows.stoswindow import StosWindow

    for vt in (ViewType.Composite, ViewType.Source, ViewType.Target):
        if vt not in window_manager:
            continue
        win = window_manager[vt]
        if not isinstance(win, StosWindow) or not win.isVisible():
            continue
        glpanel = win.imagepanel.glcanvas
        if exclude_gl_panel is not None and glpanel is exclude_gl_panel:
            continue
        glpanel.repaint()

    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is not None:
        app.processEvents()


@inject
def RotateTranslateWarpedImage(source_image_key: str,
                               target_image_key: str,
                               settings: StosBruteSettings,
                               LimitImageSize: bool = False,
                               method: SliceToSliceMethod | None = None,
                               image_manager: IImageManager = Provide[IContainer.image_manager],
                               app_settings: AppSettings = Provide[IContainer.settings]) -> ITransform | None:
    """Run rigid (rotate+translate) alignment between source and target images; returns ITransform or None if images missing."""
    logger.debug(
        "RotateTranslateWarpedImage entry source=%s target=%s method=%s",
        source_image_key,
        target_image_key,
        method if method is not None else settings.method,
    )
    largestdimension = 2047
    if LimitImageSize:
        largestdimension = 818

    if source_image_key not in image_manager:
        print("Source image not loaded")
        logger.warning("RotateTranslateWarpedImage missing source image key=%s", source_image_key)
        return

    if target_image_key not in image_manager:
        print("Target image not loaded")
        logger.warning("RotateTranslateWarpedImage missing target image key=%s", target_image_key)
        return

    stos_settings = app_settings.stos
    source_settings_path = (
        stos_settings.source_image.image_fullpath if stos_settings.source_image is not None else None
    )
    target_settings_path = (
        stos_settings.target_image.image_fullpath if stos_settings.target_image is not None else None
    )
    warped_image, fixed_image = resolve_warped_and_fixed_image_data(
        image_manager=image_manager,
        source_image_key=source_image_key,
        target_image_key=target_image_key,
        stos_filename=stos_settings.stos_filename,
        settings_source_image_path=source_settings_path,
        settings_target_image_path=target_settings_path,
    )
    working_settings = copy.copy(settings)
    if method is not None:
        working_settings.method = method
    if LimitImageSize:
        working_settings.larget_dimension = largestdimension
    alignRecord = stos.SliceToSliceRigidRegistrationWithPreprocessedImages(source_image_data=warped_image,
                                                                           target_image_data=fixed_image,
                                                                           settings=working_settings,
                                                                           SingleThread=True,
                                                                           Cluster=False,
                                                                           )
    # alignRecord = IrTools.alignment_record.AlignmentRecord((22.67, -4), 100, -132.5)
    print("Alignment found: " + str(alignRecord))
    spatial_transform = alignRecord.ToSpatialTransform(source_shape=warped_image.shape,
                                                       target_shape=fixed_image.shape)
    transform = alignRecord.ToImageTransform(source_image_shape=warped_image.shape,
                                             target_image_shape=fixed_image.shape)
    logger.debug("RotateTranslateWarpedImage returning transform=%s flip_ud=%s angle_deg=%s",
                 type(transform).__name__,
                 getattr(transform, 'flip_ud', None),
                 numpy.degrees(getattr(transform, 'angle', 0.0)))
    return normalize_rigid_transform_for_pyre_editing(transform)
    # pyre.state.currentStosConfig._transform_controller.SetPoints(transform.points)

    # pyre.history.SaveState(pyre.state.currentStosConfig._transform_controller.transform,
    # pyre.state.currentStosConfig._transform_controller.transform)


def GridRefineTransform(settings: GridRefinement | None):
    """Refine the current STOS transform using grid refinement. Updates TransformController.TransformModel in place."""
    if settings is None:
        return
    config = pyre.state.get_current_stos_config()
    if config is None:
        return
    try:
        updatedTransform = nornir_imageregistration.RefineTransform(
            config.TransformController.TransformModel,
            settings=settings,
            SaveImages=False,
            SavePlots=True,
            outputDir=tempfile.gettempdir())

        config.TransformController.TransformModel = updatedTransform
        # pyre.history.SaveState(pyre.state.currentStosConfig._transform_controller.SetPoints,
    #                               pyre.state.currentStosConfig._transform_controller.points)
    except Exception as e:
        logger.exception("Exception running grid refinement")
        raise


@inject
def LinearBlendTransform(blend_factor: float,
                         command_history: ICommandHistory = Provide[IContainer.command_history]):
    """Blend the current control-point transform toward linear by blend_factor; saves state for undo."""
    config = pyre.state.get_current_stos_config()
    if config is None:
        return
    if not isinstance(config.Transform, IControlPoints):
        logger.warning("Linear blend requires control point based transform")
        return

    command_history.SaveState(config.TransformController.__setattr__,
                              'TransformModel',
                              config.TransformController.TransformModel)

    updated_transform = transform_utils.BlendWithLinear(
        config.Transform,
        blend_factor, ignore_rotation=False)

    config.TransformController.TransformModel = updated_transform
    print(f"Linear blend completed for blend value {blend_factor}")


def either_roi_is_masked(transform: ITransform,
                         target_mask: NDArray | None,
                         source_mask: NDArray | None,
                         target_controlpoint: PointLike,
                         alignmentArea: AreaLike,
                         ):
    """Returns True if either mask is all False"""

    if target_mask is not None and source_mask is not None:
        target_mask_roi, source_mask_roi = nornir_imageregistration.local_distortion_correction.BuildAlignmentROIs(
            transform=transform,
            targetImage_param=target_mask,
            sourceImage_param=source_mask,
            target_image_stats=None,
            source_image_stats=None,
            target_controlpoint=target_controlpoint,  # type: ignore[arg-type]
            alignmentArea=alignmentArea)  # type: ignore[arg-type]

        if not numpy.any(target_mask_roi):
            return True

        if not numpy.any(source_mask_roi):
            return True

    return False


def StartAttemptAlignPoint(pool: nornir_pools.poolbase,  # type: ignore[type-arg]
                           task_description: str,
                           transform: ITransform,
                           target_image: NDArray,
                           source_image: NDArray,
                           target_mask: NDArray | None,
                           source_mask: NDArray | None,
                           target_image_stats: ImageStats,
                           source_image_stats: ImageStats,
                           target_controlpoint,
                           alignmentArea: NDArray | tuple[float, float],
                           anglesToSearch: Iterable[float]):
    """Start an async alignment attempt for one control point. Returns None if ROI is masked; otherwise returns the task."""
    if either_roi_is_masked(transform, target_mask, source_mask, target_controlpoint, alignmentArea):
        return None

    if pool is None:
        if nornir_imageregistration.in_debug_mode():
            pool = nornir_pools.GetGlobalSerialPool()
        else:
            pool = nornir_pools.GetGlobalLocalMachinePool()

    task = nornir_imageregistration.local_distortion_correction.StartAttemptAlignPoint(pool,  # type: ignore[arg-type]
                                                                                       task_description,
                                                                                       transform=transform,
                                                                                       targetImage=target_image,
                                                                                       sourceImage=source_image,
                                                                                       target_image_stats=target_image_stats,
                                                                                       source_image_stats=source_image_stats,
                                                                                       target_controlpoint=target_controlpoint,
                                                                                       alignmentArea=alignmentArea,
                                                                                       anglesToSearch=anglesToSearch)

    return task


def FindIndiciesOutsideImage(points: NDArray, image: NDArray):
    '''
    :param ndarray points: A nx2 array of coordinates in the image
    :param ndarray image: A nxm image
    :return: An nx1 array of bits, where 1 indicates the point was outside the image boundaries
    '''
    dims = image.shape
    outside = numpy.greater_equal(points, image.shape)
    too_large = numpy.any(outside, axis=1)

    outside_small = numpy.less(points, numpy.asarray([0, 0], dtype=numpy.int32))
    too_small = numpy.any(outside_small, axis=1)

    return numpy.maximum(too_large, too_small)


def ClearPointsOnMask(transform: ITransform, FixedMaskImage: NDArray,
                      WarpedMaskImage: NDArray):
    '''Remove all transform points that are positioned in the mask image'''

    if FixedMaskImage is not None:
        SourcePoints = transform.TransformModel.SourcePoints  # type: ignore[attr-defined]
        NumPoints = SourcePoints.shape[0]
        SourcePointIndicies = numpy.asarray(numpy.floor(SourcePoints), dtype=numpy.int32)

        OutOfBounds = FindIndiciesOutsideImage(SourcePointIndicies, FixedMaskImage)

        Indicies = numpy.asarray(range(0, len(OutOfBounds)), dtype=numpy.int32)

        OutOfBoundsIndicies = Indicies[OutOfBounds]

        SourcePointsAndIndex = numpy.hstack(
            (SourcePoints, numpy.asarray(range(0, NumPoints), dtype=numpy.int32).reshape(NumPoints, 1))).astype(
            numpy.int32, copy=False)

        # transform.RemovePoints(OutOfBounds)
        InBoundsPointsAndIndex = SourcePointsAndIndex[OutOfBounds == 0, :]

        SourcePointsInMask = FixedMaskImage[InBoundsPointsAndIndex[:, 0], InBoundsPointsAndIndex[:, 1]]
        SourcePointsToRemove = SourcePointsInMask == 0
        MaskedPointIndicies = InBoundsPointsAndIndex[SourcePointsToRemove, 2]

        AllMaskedIndicies = numpy.concatenate((OutOfBoundsIndicies, MaskedPointIndicies))
        AllMaskedIndicies.sort()
        transform.RemovePoints(AllMaskedIndicies)  # type: ignore[attr-defined]

    if WarpedMaskImage is not None:
        SourcePoints = transform.TransformModel.SourcePoints  # type: ignore[attr-defined]
        NumPoints = SourcePoints.shape[0]
        SourcePointIndicies = numpy.asarray(numpy.floor(SourcePoints), dtype=numpy.int32)

        OutOfBounds = FindIndiciesOutsideImage(SourcePointIndicies, WarpedMaskImage)

        Indicies = numpy.asarray(range(0, len(OutOfBounds)), dtype=numpy.int32)

        OutOfBoundsIndicies = Indicies[OutOfBounds]

        SourcePointsAndIndex = numpy.hstack(
            (SourcePoints, numpy.asarray(range(0, NumPoints), dtype=numpy.int32).reshape(NumPoints, 1))).astype(
            numpy.int32, copy=False)

        # transform.RemovePoints(OutOfBounds)
        InBoundsPointsAndIndex = SourcePointsAndIndex[OutOfBounds == 0, :]

        SourcePointsInMask = WarpedMaskImage[InBoundsPointsAndIndex[:, 0], InBoundsPointsAndIndex[:, 1]]
        SourcePointsToRemove = SourcePointsInMask == 0
        MaskedPointIndicies = InBoundsPointsAndIndex[SourcePointsToRemove, 2]

        AllMaskedIndicies = numpy.concatenate((OutOfBoundsIndicies, MaskedPointIndicies))
        AllMaskedIndicies.sort()
        transform.RemovePoints(AllMaskedIndicies)  # type: ignore[attr-defined]
