'''
Created on Oct 16, 2012

@author: u0490822
'''
import logging
import tempfile
import copy
import threading
from typing import Iterable, Sequence

logger = logging.getLogger(__name__)

from dependency_injector.wiring import Provide, inject
import numpy
import numpy as np
from numpy.typing import NDArray
from PyQt6.QtWidgets import QWidget

import nornir_imageregistration
from nornir_imageregistration import cp
from nornir_imageregistration import ITransform, PointLike, AreaLike, ImageStats, StosFile
from nornir_imageregistration.settings import StosBruteSettings, GridRefinement, SliceToSliceMethod
from nornir_imageregistration.transforms import IControlPoints
from nornir_imageregistration.transforms import utils as transform_utils
from nornir_imageregistration.refine_shared.progress import snapshot_transform_for_preview
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
from pyre.stos_registration import normalize_rigid_transform_for_pyre_editing, resolve_source_and_target_image_data


def SaveRegisteredWarpedImage(
        fileFullPath: str,
        transform: ITransform,
        fixed_image_shape: Sequence[int],
        warpedImage: NDArray) -> None:
    """Save the warped image registered into fixed space to a file."""
    registeredImage = AssembleHugeRegisteredWarpedImage(
        transform,
        fixed_image_shape,
        warpedImage,
    )
    nornir_imageregistration.SaveImage(fileFullPath, registeredImage)


def AssembleHugeRegisteredWarpedImage(
        transform: ITransform,
        fixedImageShape: NDArray | Sequence[int],
        warpedImage: NDArray) -> NDArray:
    """Apply transform to warped image and assemble into fixed space. Cuts image into tiles for large data."""
    shape = numpy.asarray(fixedImageShape, dtype=numpy.int64)
    return assemble.TransformImage(
        transform,
        shape,
        warpedImage,
        CropUndefined=False,
        interpolation_order=1,
        extrapolate=False,
        enforce_background_cval=0,
    )


def stos_image_dim_from_shape(shape: Sequence[int]) -> list[float]:
    """Build a STOS image dim tuple from ndarray shape (height, width)."""
    height, width = int(shape[0]), int(shape[1])
    return [1.0, 1.0, float(width), float(height)]


def build_stos_object_for_save(
        target_image_fullpath: str,
        source_image_fullpath: str,
        transform: ITransform,
        target_mask_fullpath: str | None = None,
        source_mask_fullpath: str | None = None,
        *,
        control_image_dim: list[float] | None = None,
        mapped_image_dim: list[float] | None = None,
) -> StosFile:
    """Snapshot transform and image paths on the main thread before background Save."""
    stos_obj = StosFile.Create(
        target_image_fullpath,
        source_image_fullpath,
        transform,
        target_mask_fullpath,
        source_mask_fullpath,
    )
    if control_image_dim is not None:
        stos_obj.ControlImageDim = list(control_image_dim)
    if mapped_image_dim is not None:
        stos_obj.MappedImageDim = list(mapped_image_dim)
    return stos_obj


def save_stos_object(stos_obj: StosFile, fullpath: str) -> str:
    """Write a prepared StosFile to disk. Safe to call from a worker thread."""
    stos_obj.Save(fullpath)
    return fullpath


def stos_image_dims_from_stos_config(
        stos_config,
) -> tuple[list[float] | None, list[float] | None]:
    """Read control/mapped image dims from loaded STOS view models when available."""
    control_dim: list[float] | None = None
    mapped_dim: list[float] | None = None
    if stos_config is None:
        return control_dim, mapped_dim
    source_vm = getattr(stos_config, "SourceImageViewModel", None) or getattr(
        stos_config, "FixedImageViewModel", None
    )
    target_vm = getattr(stos_config, "TargetImageViewModel", None) or getattr(
        stos_config, "WarpedImageViewModel", None
    )
    if source_vm is not None and getattr(source_vm, "Image", None) is not None:
        control_dim = stos_image_dim_from_shape(source_vm.Image.shape)
    if target_vm is not None and getattr(target_vm, "Image", None) is not None:
        mapped_dim = stos_image_dim_from_shape(target_vm.Image.shape)
    return control_dim, mapped_dim


def SyncWindows(LookAt, scale: float, window_manager: IWindowManager) -> None:
    """Make all STOS windows look at the same spot with the same magnification.

    ``LookAt`` is in Target (control / fixed) space. Each window's
    ``lookatfixedpoint`` converts into that panel's camera space.

    ``window_manager`` must register ViewType Source, Target, and Composite.
    """
    if not (
        ViewType.Composite in window_manager
        and ViewType.Source in window_manager
        and ViewType.Target in window_manager
    ):
        raise ValueError("window_manager must register Source, Target, and Composite views")
    for vt in (ViewType.Composite, ViewType.Source, ViewType.Target):
        window_manager[vt].lookatfixedpoint(LookAt, scale)


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


REFINE_ANGLE_HALF_WIDTH_DEG: float = 5.0
REFINE_ANGLE_STEP_DEG: float = 1.0
REFINE_RIGID_LARGEST_DIMENSION: int = 818


def build_refine_angle_grid_deg(
        center_angle_deg: float,
        half_width_deg: float = REFINE_ANGLE_HALF_WIDTH_DEG,
        step_deg: float = REFINE_ANGLE_STEP_DEG,
) -> NDArray[numpy.floating]:
    """Build an absolute angle search grid centered on ``center_angle_deg``."""
    return numpy.arange(
        center_angle_deg - half_width_deg,
        center_angle_deg + half_width_deg + step_deg * 0.5,
        step_deg,
        dtype=float,
    )


def _preserve_rigid_refine_attributes(
        result: ITransform,
        current: ITransform,
        *,
        lock_scale: bool,
) -> ITransform:
    """Normalize result for editing and optionally lock scale / flip from current."""
    result = normalize_rigid_transform_for_pyre_editing(result)
    current = normalize_rigid_transform_for_pyre_editing(current)
    if not isinstance(result, nornir_imageregistration.transforms.CenteredSimilarity2DTransform):
        result = nornir_imageregistration.transforms.ConvertRigidTransformToCenteredSimilarityTransform(
            result)

    current_flip = bool(getattr(current, "flip_ud", False))
    result_flip = bool(getattr(result, "flip_ud", False))
    # Local refine disables try_flipped; keep the user's flip unless brute changed it.
    if result_flip == current_flip or not result_flip:
        result._flip_ud = current_flip  # type: ignore[attr-defined]

    if lock_scale:
        result._scalar = float(getattr(current, "scalar", 1.0))  # type: ignore[attr-defined]

    # Keep the current interactive pivot when present; offset/angle come from brute.
    current_center = getattr(current, "source_space_center_of_rotation", None)
    if current_center is not None:
        result._source_space_center_of_rotation = numpy.asarray(  # type: ignore[attr-defined]
            current_center, dtype=numpy.float32).copy()
    result._update_transform_matrix()  # type: ignore[attr-defined]
    result.OnTransformChanged()  # type: ignore[attr-defined]
    return result


@inject
def RefineRigidTransformLocal(
        current_transform: ITransform,
        refine_scale: bool = False,
        source_image_key: str = "Source",
        target_image_key: str = "Target",
        image_manager: IImageManager = Provide[IContainer.image_manager],
        app_settings: AppSettings = Provide[IContainer.settings],
        cancel_event: threading.Event | None = None,
        progress_callback=None,
) -> ITransform | None:
    """Local BruteForce rigid refine around the current angle (±5° at 1° steps).

    When ``refine_scale`` is False, the current isotropic scale is preserved.
    When True, scale is refined using the current scalar as ``initial_scale_hint``.
    """
    if not isinstance(current_transform, nornir_imageregistration.IRigidTransform):
        raise TypeError("Local rigid refinement requires a rigid transform")

    current_transform = normalize_rigid_transform_for_pyre_editing(current_transform)
    if source_image_key not in image_manager:
        logger.warning("RefineRigidTransformLocal missing source image key=%s", source_image_key)
        return None
    if target_image_key not in image_manager:
        logger.warning("RefineRigidTransformLocal missing target image key=%s", target_image_key)
        return None

    stos_settings = app_settings.stos
    source_settings_path = (
        stos_settings.source_image.image_fullpath if stos_settings.source_image is not None else None
    )
    target_settings_path = (
        stos_settings.target_image.image_fullpath if stos_settings.target_image is not None else None
    )
    warped_image, fixed_image = resolve_source_and_target_image_data(
        image_manager=image_manager,
        source_image_key=source_image_key,
        target_image_key=target_image_key,
        stos_filename=stos_settings.stos_filename,
        settings_source_image_path=source_settings_path,
        settings_target_image_path=target_settings_path,
    )
    from pyre.image_contrast import contrasted_permutation_helper
    warped_image = contrasted_permutation_helper(warped_image, app_settings.ui.source_contrast)
    fixed_image = contrasted_permutation_helper(fixed_image, app_settings.ui.target_contrast)

    center_deg = float(numpy.degrees(getattr(current_transform, "angle", 0.0)))
    angle_grid = build_refine_angle_grid_deg(center_deg)
    current_scale = float(getattr(current_transform, "scalar", 1.0))

    working_settings = copy.copy(stos_settings.brute_registration)
    working_settings.method = SliceToSliceMethod.BruteForce
    working_settings.angles = [float(a) for a in angle_grid]
    working_settings.larget_dimension = REFINE_RIGID_LARGEST_DIMENSION
    working_settings.try_flipped = False
    working_settings.initial_scale_hint = current_scale
    working_settings.estimated_scale_hint = None

    align_record = stos.SliceToSliceRigidRegistrationWithPreprocessedImages(
        source_image_data=warped_image,
        target_image_data=fixed_image,
        settings=working_settings,
        SingleThread=True,
        Cluster=False,
        cancel_event=cancel_event,
        progress_callback=progress_callback,
    )
    logger.info("Local rigid refine alignment: %s", align_record)
    transform = align_record.ToImageTransform(
        source_image_shape=warped_image.shape,
        target_image_shape=fixed_image.shape,
    )
    return _preserve_rigid_refine_attributes(
        transform, current_transform, lock_scale=not refine_scale)


@inject
def RotateTranslateWarpedImage(source_image_key: str,
                               target_image_key: str,
                               settings: StosBruteSettings,
                               LimitImageSize: bool = False,
                               method: SliceToSliceMethod | None = None,
                               image_manager: IImageManager = Provide[IContainer.image_manager],
                               app_settings: AppSettings = Provide[IContainer.settings],
                               cancel_event: threading.Event | None = None,
                               progress_callback=None) -> ITransform | None:
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
        logger.warning("RotateTranslateWarpedImage missing source image key=%s", source_image_key)
        return

    if target_image_key not in image_manager:
        logger.warning("RotateTranslateWarpedImage missing target image key=%s", target_image_key)
        return

    stos_settings = app_settings.stos
    source_settings_path = (
        stos_settings.source_image.image_fullpath if stos_settings.source_image is not None else None
    )
    target_settings_path = (
        stos_settings.target_image.image_fullpath if stos_settings.target_image is not None else None
    )
    warped_image, fixed_image = resolve_source_and_target_image_data(
        image_manager=image_manager,
        source_image_key=source_image_key,
        target_image_key=target_image_key,
        stos_filename=stos_settings.stos_filename,
        settings_source_image_path=source_settings_path,
        settings_target_image_path=target_settings_path,
    )
    from pyre.image_contrast import contrasted_permutation_helper
    warped_image = contrasted_permutation_helper(warped_image, app_settings.ui.source_contrast)
    fixed_image = contrasted_permutation_helper(fixed_image, app_settings.ui.target_contrast)
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
                                                                           cancel_event=cancel_event,
                                                                           progress_callback=progress_callback,
                                                                           )
    # alignRecord = IrTools.alignment_record.AlignmentRecord((22.67, -4), 100, -132.5)
    logger.info("Alignment found: %s", alignRecord)
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


def create_pyre_grid_refinement_settings(
        source_img_data: nornir_imageregistration.ImagePermutationHelper,
        target_img_data: nornir_imageregistration.ImagePermutationHelper,
        *,
        num_iterations: int | None = None,
        grid_spacing: int | NDArray[np.integer] | Iterable[int] | None = None,
        cell_size: int | NDArray[np.integer] | Iterable[int] | None = None,
        angles_to_search: Iterable[float] | NDArray[np.floating] | None = None,
) -> GridRefinement:
    """Build STOS grid-refine settings that stay on host arrays.

    Pyre loads mosaics as NumPy for OpenGL. Forcing ``cupy_processing=False``
    keeps RefineTransform off CUDA so the job thread does not share the GPU
    with ``paintGL``. ``single_thread_processing`` stays False so images go to
    shared memory and per-cell work uses the CPU pool, matching buildmanager
    CPU refine. Buildmanager still uses the default ``UsingCupy()`` upload.
    """
    return GridRefinement.CreateWithPreprocessedImages(
        source_img_data=source_img_data,
        target_img_data=target_img_data,
        num_iterations=num_iterations,
        grid_spacing=grid_spacing,
        cell_size=cell_size,
        angles_to_search=angles_to_search,
        cupy_processing=False,
        single_thread_processing=False,
    )


def compute_grid_refine_transform(
        transform: ITransform,
        settings: GridRefinement,
        cancel_event: threading.Event | None = None,
        progress_callback=None,
        save_plots: bool = True) -> ITransform:
    """Run grid refine for *transform* using *settings*; intended for background workers.

    Forwards *progress_callback* so ``RefineTransform`` can preview each pass.
    Planned pass count is ``settings.num_iterations`` in this one call — do not
    emulate N iterations with N one-pass jobs.
    """
    with settings:
        result = nornir_imageregistration.RefineTransform(
            transform,
            settings=settings,
            SaveImages=False,
            SavePlots=save_plots,
            outputDir=tempfile.gettempdir(),
            cancel_event=cancel_event,
            progress_callback=progress_callback,
        )
        # Convert on this worker thread: GUI paint must not use CuPy arrays
        # allocated here (cudaErrorIllegalAddress).
        host = snapshot_transform_for_preview(result)
        return host if host is not None else result


def GridRefineTransform(settings: GridRefinement | None):
    """Refine the current STOS transform using grid refinement. Updates TransformController.TransformModel in place."""
    if settings is None:
        return
    config = pyre.state.get_current_stos_config()
    if config is None:
        return
    try:
        updatedTransform = compute_grid_refine_transform(
            snapshot_transform_for_preview(config.TransformController.TransformModel)
            or config.TransformController.TransformModel,
            settings)
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
    logger.info("Linear blend completed for blend value %s", blend_factor)


def either_roi_is_masked(transform: ITransform,
                         target_mask: NDArray | None,
                         source_mask: NDArray | None,
                         target_controlpoint: PointLike,
                         alignmentArea: AreaLike,
                         ):
    """Returns True if either mask is all False"""

    if target_mask is not None and source_mask is not None:
        # Warp the masks through the same local rigid approximation AttemptAlignPoint uses
        # for the image ROIs. Warping through the full mesh/RBF transform here cost ~18s
        # per point versus ~2s, and sampled a different mapping than the ROIs being checked.
        rigid_transform = nornir_imageregistration.local_distortion_correction.ApproximateRigidTransformByTargetPoints(
            input_transform=transform,
            target_points=target_controlpoint,  # type: ignore[arg-type]
            cell_size=alignmentArea)  # type: ignore[arg-type]

        target_mask_roi, source_mask_roi = nornir_imageregistration.local_distortion_correction.BuildAlignmentROIs(
            transform=rigid_transform[0],
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
                           anglesToSearch: Iterable[float],
                           estimate_angle: bool = False):
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
                                                                                       anglesToSearch=anglesToSearch,
                                                                                       estimate_angle=estimate_angle)

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


def _indices_to_remove_for_mask(
        points: NDArray,
        mask_image: NDArray) -> NDArray:
    """Return point indices that fall outside the mask image or on masked (zero) pixels."""
    xp = cp.get_array_module(points)
    point_indices = nornir_imageregistration.EnsureNumpyArray(
        xp.floor(points), dtype=np.int32)
    host_points = nornir_imageregistration.EnsureNumpyArray(points)
    num_points = host_points.shape[0]

    out_of_bounds = FindIndiciesOutsideImage(point_indices, mask_image)
    index_range = np.asarray(range(0, len(out_of_bounds)), dtype=np.int32)
    out_of_bounds_indices = index_range[out_of_bounds]

    points_and_index = np.hstack(
        (host_points, np.asarray(range(0, num_points), dtype=np.int32).reshape(num_points, 1))).astype(
        np.int32, copy=False)
    in_bounds_points_and_index = points_and_index[out_of_bounds == 0, :]

    points_in_mask = mask_image[in_bounds_points_and_index[:, 0], in_bounds_points_and_index[:, 1]]
    masked_point_indices = in_bounds_points_and_index[points_in_mask == 0, 2]

    all_masked_indices = np.concatenate((out_of_bounds_indices, masked_point_indices))
    all_masked_indices.sort()
    return all_masked_indices


def ClearPointsOnMask(transform: ITransform, FixedMaskImage: NDArray,
                      WarpedMaskImage: NDArray):
    '''Remove all transform points that are positioned in the mask image'''

    if FixedMaskImage is not None:
        fixed_points = transform.TransformModel.TargetPoints  # type: ignore[attr-defined]
        transform.RemovePoints(_indices_to_remove_for_mask(fixed_points, FixedMaskImage))  # type: ignore[attr-defined]

    if WarpedMaskImage is not None:
        warped_points = transform.TransformModel.SourcePoints  # type: ignore[attr-defined]
        transform.RemovePoints(_indices_to_remove_for_mask(warped_points, WarpedMaskImage))  # type: ignore[attr-defined]
