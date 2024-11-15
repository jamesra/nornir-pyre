'''
Created on Oct 16, 2012

@author: u0490822
'''
from typing import Iterable

from dependency_injector.wiring import Provide, inject
import numpy
from numpy.typing import NDArray

import nornir_imageregistration
import nornir_imageregistration.assemble as assemble
import nornir_imageregistration.stos_brute as stos
import nornir_pools
import pyre
from pyre.container import IContainer
from pyre.interfaces.managers.command_history import ICommandHistory


def SaveRegisteredWarpedImage(fileFullPath: str, transform: nornir_imageregistration.ITransform, warpedImage: NDArray):
    # registeredImage = assemble.WarpedImageToFixedSpace(transform, Config.FixedImageArray.Image.shape, Config.WarpedImageArray.Image)
    registeredImage = AssembleHugeRegisteredWarpedImage(transform,
                                                        pyre.state.currentStosConfig.FixedImageViewModel.Image.shape,
                                                        pyre.state.currentStosConfig.WarpedImageViewModel.Image)

    nornir_imageregistration.ImageSave(fileFullPath, registeredImage)


def AssembleHugeRegisteredWarpedImage(transform: nornir_imageregistration.ITransform, fixedImageShape: NDArray,
                                      warpedImage: NDArray):
    '''Cut image into tiles, assemble small chunks'''

    return assemble.TransformImage(transform, fixedImageShape, warpedImage, CropUndefined=False)


def SyncWindows(LookAt, scale: float):
    '''Make all windows look at the same spot with the same magnification, LookAt point should be in fixed space'''
    #    Config.CompositeWin.camera.x = LookAt[0]
    #    Config.CompositeWin.camera.y = LookAt[1]
    #    Config.CompositeWin.camera.scale = scale
    pyre.Windows['Composite'].imagepanel.camera.x = LookAt[0]
    pyre.Windows['Composite'].imagepanel.camera.y = LookAt[1]
    pyre.Windows['Composite'].imagepanel.camera.scale = scale

    #    Config.FixedWindow.camera.x = LookAt[0]
    #    Config.FixedWindow.camera.y = LookAt[1]
    #    Config.FixedWindow.camera.scale = scale
    pyre.Windows['Fixed'].imagepanel.camera.x = LookAt[0]
    pyre.Windows['Fixed'].imagepanel.camera.y = LookAt[1]
    pyre.Windows['Fixed'].imagepanel.camera.scale = scale

    #    warpedLookAt = LookAt
    #    if(not Config.WarpedWindow.ShowWarped):
    #        warpedLookAt = Config.CurrentTransform.InverseTransform([LookAt])
    #        warpedLookAt = warpedLookAt[0]

    warpedLookAt = LookAt
    if pyre.Windows['Warped'].IsShown():
        warpedLookAt = pyre.state.currentStosConfig._TransformViewModel.InverseTransform([LookAt])
        warpedLookAt = warpedLookAt[0]

    #    Config.WarpedWindow.camera.x = warpedLookAt[0]
    #    Config.WarpedWindow.camera.y = warpedLookAt[1]
    #    Config.WarpedWindow.camera.scale = scale
    pyre.Windows['Warped'].imagepanel.camera.x = LookAt[0]
    pyre.Windows['Warped'].imagepanel.camera.y = LookAt[1]
    pyre.Windows['Warped'].imagepanel.camera.scale = scale


def RotateTranslateWarpedImage(LimitImageSize: bool = False):
    largestdimension = 2047
    if LimitImageSize:
        largestdimension = 818

    if not (pyre.state.currentStosConfig.FixedImageViewModel is None or
            pyre.state.currentStosConfig.WarpedImageViewModel is None):
        alignRecord = stos.SliceToSliceBruteForce(pyre.state.currentStosConfig.FixedImages.Image,
                                                  pyre.state.currentStosConfig.WarpedImages.Image,
                                                  pyre.state.currentStosConfig.FixedImages.Mask,
                                                  pyre.state.currentStosConfig.WarpedImages.Mask,
                                                  LargestDimension=largestdimension,
                                                  TestFlip=False,
                                                  Cluster=False)
        # alignRecord = IrTools.alignment_record.AlignmentRecord((22.67, -4), 100, -132.5)
        print("Alignment found: " + str(alignRecord))
        transform = alignRecord.ToImageTransform(pyre.state.currentStosConfig.FixedImageViewModel.RawImageSize,
                                                 pyre.state.currentStosConfig.WarpedImageViewModel.RawImageSize)
        pyre.state.currentStosConfig.TransformController.TransformModel = transform
        # pyre.state.currentStosConfig._transform_controller.SetPoints(transform.points)

        # pyre.history.SaveState(pyre.state.currentStosConfig._transform_controller.transform,
        # pyre.state.currentStosConfig._transform_controller.transform)


def GridRefineTransform(settings: nornir_imageregistration.settings.GridRefinement | None):
    if settings is None:
        return

    try:
        updatedTransform = nornir_imageregistration.RefineTransform(
            pyre.state.currentStosConfig.TransformController.TransformModel,
            settings=settings,
            SaveImages=False,
            SavePlots=False,
            outputDir=None)

        pyre.state.currentStosConfig.TransformController.TransformModel = updatedTransform
        # pyre.history.SaveState(pyre.state.currentStosConfig._transform_controller.SetPoints,
    #                               pyre.state.currentStosConfig._transform_controller.points)
    except Exception as e:
        print(f"Exception running grid refinement:\n{e}")
        pass


@inject
def LinearBlendTransform(blend_factor: float,
                         command_history: ICommandHistory = Provide[IContainer.command_history]):
    if not isinstance(pyre.state.currentStosConfig.Transform, nornir_imageregistration.transforms.IControlPoints):
        print("Linear blend requires control point based transform")
        return

    command_history.SaveState(pyre.state.currentStosConfig.TransformController.__setattr__,
                              'TransformModel',
                              pyre.state.currentStosConfig.TransformController.TransformModel)

    updated_transform = nornir_imageregistration.transforms.utils.BlendWithLinear(
        pyre.state.currentStosConfig.Transform,
        blend_factor, ignore_rotation=False)

    pyre.state.currentStosConfig.TransformController.TransformModel = updated_transform
    print(f"Linear blend completed for blend value {blend_factor}")


def either_roi_is_masked(transform: nornir_imageregistration.ITransform,
                         target_mask: NDArray | None,
                         source_mask: NDArray | None,
                         target_controlpoint: nornir_imageregistration.PointLike,
                         alignmentArea: nornir_imageregistration.AreaLike,
                         ):
    """Returns True if either mask is all False"""

    if target_mask is not None and source_mask is not None:
        target_mask_roi, source_mask_roi = nornir_imageregistration.local_distortion_correction.BuildAlignmentROIs(
            transform=transform,
            targetImage_param=target_mask,
            sourceImage_param=source_mask,
            target_image_stats=None,
            source_image_stats=None,
            target_controlpoint=target_controlpoint,
            alignmentArea=alignmentArea)

        if not numpy.any(target_mask_roi):
            return True

        if not numpy.any(source_mask_roi):
            return True

    return False


def StartAttemptAlignPoint(pool: nornir_pools.poolbase,
                           task_description: str,
                           transform: nornir_imageregistration.ITransform,
                           target_image: NDArray,
                           source_image: NDArray,
                           target_mask: NDArray | None,
                           source_mask: NDArray | None,
                           target_image_stats: nornir_imageregistration.ImageStats,
                           source_image_stats: nornir_imageregistration.ImageStats,
                           target_controlpoint,
                           alignmentArea: NDArray | tuple[float, float],
                           anglesToSearch: Iterable[float]):
    if either_roi_is_masked(transform, target_mask, source_mask, target_controlpoint, alignmentArea):
        return None

    if pool is None:
        pool = nornir_pools.GetGlobalLocalMachinePool()

    '''Try to use the Composite view to render the two tiles we need for alignment'''
    task = nornir_imageregistration.local_distortion_correction.StartAttemptAlignPoint(pool,
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


#
#     FixedRectangle = nornir_imageregistration.Rectangle.CreateFromPointAndArea(point=[controlpoint[0] - (alignmentArea[0] / 2.0),
#                                                                                    controlpoint[1] - (alignmentArea[1] / 2.0)],
#                                                                              area=alignmentA rea)
# 
#     FixedRectangle = nornir_imageregistration.Rectangle.SafeRound(FixedRectangle)
#     FixedRectangle = nornir_imageregistration.Rectangle.change_area(FixedRectangle, alignmentArea)
#     
#     # Pull image subregions 
#     rigid_transforms = nornir_imageregistration.local_distortion_correction.ApproximateRigidTransform(input_transform=transform,
#                                                                                                       target_points=controlpoint)
#     
#     warpedImageROI = assemble.WarpedImageToFixedSpace(rigid_transforms[0],
#                             fixedImage.shape, warpedImage, botleft=FixedRectangle.BottomLeft, area=FixedRectangle.Size, extrapolate=True)
# 
#     fixedImageROI = nornir_imageregistration.CropImage(fixedImage, FixedRectangle.BottomLeft[1], FixedRectangle.BottomLeft[0], int(FixedRectangle.Size[1]), int(FixedRectangle.Size[0]))
# 
#     nornir_imageregistration.ShowGrayscale([fixedImageROI, warpedImageROI])
# 
#     # pool = Pools.GetGlobalMultithreadingPool()
# 
#     # task = pool.add_task("AttemptAlignPoint", core.FindOffset, fixedImageROI, warpedImageROI, MinOverlap = 0.2)
#     # apoint = task.wait_return()
#     # apoint = core.FindOffset(fixedImageROI, warpedImageROI, MinOverlap=0.2)
#     #nornir_imageregistration.ShowGrayscale([fixedImageROI, warpedImageROI], "Fixed <---> Warped")
#  
#     apoint = stos.SliceToSliceBruteForce(fixedImageROI, warpedImageROI, AngleSearchRange=anglesToSearch, MinOverlap=0.25, SingleThread=True, Cluster=False, TestFlip=False)
# 
#     print("Auto-translate result: " + str(apoint))
#     return apoint


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


def ClearPointsOnMask(transform: nornir_imageregistration.ITransform, FixedMaskImage: NDArray,
                      WarpedMaskImage: NDArray):
    '''Remove all transform points that are positioned in the mask image'''

    if FixedMaskImage is not None:
        SourcePoints = transform.TransformModel.SourcePoints
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
        transform.RemovePoints(AllMaskedIndicies)

    if WarpedMaskImage is not None:
        SourcePoints = transform.TransformModel.SourcePoints
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
        transform.RemovePoints(AllMaskedIndicies)
