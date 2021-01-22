'''
Created on Oct 16, 2012

@author: u0490822
'''
import argparse
import logging
import os
import sys

import nornir_imageregistration 
import nornir_shared.misc
import numpy 
from scipy.misc import imsave 

import pyre
import nornir_imageregistration.assemble as assemble
import nornir_imageregistration.stos_brute as stos


def SaveRegisteredWarpedImage(fileFullPath, transform, warpedImage): 

    # registeredImage = assemble.WarpedImageToFixedSpace(transform, Config.FixedImageArray.Image.shape, Config.WarpedImageArray.Image)
    registeredImage = AssembleHugeRegisteredWarpedImage(transform,
                                                        pyre.state.currentStosConfig.FixedImageViewModel.Image.shape,
                                                        pyre.state.currentStosConfig.WarpedImageViewModel.Image)

    imsave(fileFullPath, registeredImage)


def AssembleHugeRegisteredWarpedImage(transform, fixedImageShape, warpedImage):
    '''Cut image into tiles, assemble small chunks'''

    return assemble.TransformImage(transform, fixedImageShape, warpedImage)


def SyncWindows(LookAt, scale):
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
    if(pyre.Windows['Warped'].IsShown()):
        warpedLookAt = pyre.state.currentStosConfig._TransformViewModel.InverseTransform([LookAt])
        warpedLookAt = warpedLookAt[0]



#    Config.WarpedWindow.camera.x = warpedLookAt[0]
#    Config.WarpedWindow.camera.y = warpedLookAt[1]
#    Config.WarpedWindow.camera.scale = scale
    pyre.Windows['Warped'].imagepanel.camera.x = LookAt[0]
    pyre.Windows['Warped'].imagepanel.camera.y = LookAt[1]
    pyre.Windows['Warped'].imagepanel.camera.scale = scale


def RotateTranslateWarpedImage(LimitImageSize=False):

    largestdimension = 2047
    if LimitImageSize:
        largestdimension = 818

    if not (pyre.state.currentStosConfig.FixedImageViewModel is None or
            pyre.state.currentStosConfig.WarpedImageViewModel is None):
        alignRecord = stos.SliceToSliceBruteForce(pyre.state.currentStosConfig.FixedImageViewModel.Image,
                                                                 pyre.state.currentStosConfig.WarpedImageViewModel.Image,
                                                                 LargestDimension=largestdimension,
                                                                 Cluster=False)
        # alignRecord = IrTools.alignment_record.AlignmentRecord((22.67, -4), 100, -132.5)
        print("Alignment found: " + str(alignRecord))
        transform = alignRecord.ToTransform(pyre.state.currentStosConfig.FixedImageViewModel.RawImageSize,
                                             pyre.state.currentStosConfig.WarpedImageViewModel.RawImageSize)
        pyre.state.currentStosConfig.TransformController.SetPoints(transform.points)

        pyre.history.SaveState(pyre.state.currentStosConfig.TransformController.SetPoints, pyre.state.currentStosConfig.TransformController.points)


def GridRefineTransform():

    if not (pyre.state.currentStosConfig.FixedImageViewModel is None or
            pyre.state.currentStosConfig.WarpedImageViewModel is None):
        
        updatedTransform = nornir_imageregistration.RefineTransform(
                                            pyre.state.currentStosConfig.TransformController.TransformModel,
                                            target_image=pyre.state.currentStosConfig.FixedImageViewModel.Image,
                                            source_image=pyre.state.currentStosConfig.WarpedImageViewModel.Image,
                                            target_mask=pyre.state.currentStosConfig.FixedImageMaskViewModel.Image,
                                            source_mask=pyre.state.currentStosConfig.WarpedImageMaskViewModel.Image,
                                            num_iterations=None,
                                            cell_size=None,
                                            grid_spacing=None,
                                            angles_to_search=None,
                                            min_travel_for_finalization=None,
                                            min_alignment_overlap=None,
                                            SaveImages=False,
                                            SavePlots=False,
                                            outputDir=None)
                
        pyre.state.currentStosConfig.TransformController.SetPoints(updatedTransform.points)
        pyre.history.SaveState(pyre.state.currentStosConfig.TransformController.SetPoints,
                               pyre.state.currentStosConfig.TransformController.points)


def AttemptAlignPoint(transform, fixedImage, warpedImage, controlpoint, alignmentArea, anglesToSearch):
    '''Try to use the Composite view to render the two tiles we need for alignment'''
    return nornir_imageregistration.local_distortion_correction.AttemptAlignPoint(transform=transform,
                                                                                  fixedImage=fixedImage,
                                                                                  warpedImage=warpedImage,
                                                                                  controlpoint=controlpoint,
                                                                                  alignmentArea=alignmentArea,
                                                                                  anglesToSearch=anglesToSearch)
#     
#     FixedRectangle = nornir_imageregistration.Rectangle.CreateFromPointAndArea(point=[controlpoint[0] - (alignmentArea[0] / 2.0),
#                                                                                    controlpoint[1] - (alignmentArea[1] / 2.0)],
#                                                                              area=alignmentArea)
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
 

def FindIndiciesOutsideImage(points, image):
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

def ClearPointsOnMask(transform, FixedMaskImage, WarpedMaskImage):
    '''Remove all transform points that are positioned in the mask image'''

    if not FixedMaskImage is None:
        SourcePoints = transform.TransformModel.SourcePoints
        NumPoints = SourcePoints.shape[0]
        SourcePointIndicies = numpy.asarray(numpy.floor(SourcePoints), dtype=numpy.int32)

        OutOfBounds = FindIndiciesOutsideImage(SourcePointIndicies, FixedMaskImage)

        Indicies =  numpy.asarray(range(0, len(OutOfBounds)), dtype=numpy.int32)

        OutOfBoundsIndicies = Indicies[OutOfBounds]

        SourcePointsAndIndex = numpy.hstack((SourcePoints, numpy.asarray(range(0, NumPoints), dtype=numpy.int32).reshape(NumPoints,1))).astype(numpy.int32)

        #transform.RemovePoints(OutOfBounds)
        InBoundsPointsAndIndex = SourcePointsAndIndex[OutOfBounds==0, :]

        SourcePointsInMask = FixedMaskImage[InBoundsPointsAndIndex[:,0], InBoundsPointsAndIndex[:,1]]
        SourcePointsToRemove = SourcePointsInMask == 0
        MaskedPointIndicies = InBoundsPointsAndIndex[SourcePointsToRemove,2]

        AllMaskedIndicies = numpy.concatenate((OutOfBoundsIndicies, MaskedPointIndicies)) 
        AllMaskedIndicies.sort()
        transform.RemovePoints(AllMaskedIndicies)


    if not WarpedMaskImage is None:
        SourcePoints = transform.TransformModel.SourcePoints
        NumPoints = SourcePoints.shape[0]
        SourcePointIndicies = numpy.asarray(numpy.floor(SourcePoints), dtype=numpy.int32)

        OutOfBounds = FindIndiciesOutsideImage(SourcePointIndicies, WarpedMaskImage)

        Indicies =  numpy.asarray(range(0, len(OutOfBounds)), dtype=numpy.int32)

        OutOfBoundsIndicies = Indicies[OutOfBounds]

        SourcePointsAndIndex = numpy.hstack((SourcePoints, numpy.asarray(range(0, NumPoints), dtype=numpy.int32).reshape(NumPoints,1))).astype(numpy.int32)

        #transform.RemovePoints(OutOfBounds)
        InBoundsPointsAndIndex = SourcePointsAndIndex[OutOfBounds==0, :]

        SourcePointsInMask = WarpedMaskImage[InBoundsPointsAndIndex[:,0], InBoundsPointsAndIndex[:,1]]
        SourcePointsToRemove = SourcePointsInMask == 0
        MaskedPointIndicies = InBoundsPointsAndIndex[SourcePointsToRemove,2]

        AllMaskedIndicies = numpy.concatenate((OutOfBoundsIndicies, MaskedPointIndicies)) 
        AllMaskedIndicies.sort()
        transform.RemovePoints(AllMaskedIndicies)