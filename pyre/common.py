'''
Created on Oct 16, 2012

@author: u0490822
'''
import argparse
import logging
import os
import sys

import nornir_imageregistration
from nornir_imageregistration.transforms import *
import nornir_shared.misc
import numpy 
from scipy.misc import imsave
from scipy.ndimage import imread

from . import state
from pyre import history, Windows
import nornir_imageregistration.assemble as assemble
import nornir_imageregistration.stos_brute as stos


def SaveRegisteredWarpedImage(fileFullPath, transform, warpedImage): 

    # registeredImage = assemble.WarpedImageToFixedSpace(transform, Config.FixedImageArray.Image.shape, Config.WarpedImageArray.Image)
    registeredImage = AssembleHugeRegisteredWarpedImage(transform,
                                                        state.currentStosConfig.FixedImageViewModel.Image.shape,
                                                        state.currentStosConfig.WarpedImageViewModel.Image)

    imsave(fileFullPath, registeredImage)


def AssembleHugeRegisteredWarpedImage(transform, fixedImageShape, warpedImage):
    '''Cut image into tiles, assemble small chunks'''

    return assemble.TransformImage(transform, fixedImageShape, warpedImage)


def SyncWindows(LookAt, scale):
    '''Make all windows look at the same spot with the same magnification, LookAt point should be in fixed space'''
#    Config.CompositeWin.camera.x = LookAt[0]
#    Config.CompositeWin.camera.y = LookAt[1]
#    Config.CompositeWin.camera.scale = scale
    Windows['Composite'].imagepanel.camera.x = LookAt[0]
    Windows['Composite'].imagepanel.camera.y = LookAt[1]
    Windows['Composite'].imagepanel.camera.scale = scale

#    Config.FixedWindow.camera.x = LookAt[0]
#    Config.FixedWindow.camera.y = LookAt[1]
#    Config.FixedWindow.camera.scale = scale
    Windows['Fixed'].imagepanel.camera.x = LookAt[0]
    Windows['Fixed'].imagepanel.camera.y = LookAt[1]
    Windows['Fixed'].imagepanel.camera.scale = scale

#    warpedLookAt = LookAt
#    if(not Config.WarpedWindow.ShowWarped):
#        warpedLookAt = Config.CurrentTransform.InverseTransform([LookAt])
#        warpedLookAt = warpedLookAt[0]

    warpedLookAt = LookAt
    if(Windows['Warped'].IsShown()):
        warpedLookAt = state.currentStosConfig._TransformViewModel.InverseTransform([LookAt])
        warpedLookAt = warpedLookAt[0]



#    Config.WarpedWindow.camera.x = warpedLookAt[0]
#    Config.WarpedWindow.camera.y = warpedLookAt[1]
#    Config.WarpedWindow.camera.scale = scale
    Windows['Warped'].imagepanel.camera.x = LookAt[0]
    Windows['Warped'].imagepanel.camera.y = LookAt[1]
    Windows['Warped'].imagepanel.camera.scale = scale


def RotateTranslateWarpedImage(LimitImageSize=False):
    from .state import currentStosConfig

    largestdimension = 2047
    if LimitImageSize:
        largestdimension = 818

    if not (currentStosConfig.FixedImageViewModel is None or currentStosConfig.WarpedImageViewModel is None):
        alignRecord = stos.SliceToSliceBruteForce(state.currentStosConfig.FixedImageViewModel.Image,
                                                                 state.currentStosConfig.WarpedImageViewModel.Image,
                                                                  LargestDimension=largestdimension,
                                                                  Cluster=False)
        # alignRecord = IrTools.alignment_record.AlignmentRecord((22.67, -4), 100, -132.5)
        print("Alignment found: " + str(alignRecord))
        transform = alignRecord.ToTransform(state.currentStosConfig.FixedImageViewModel.RawImageSize,
                                             state.currentStosConfig.WarpedImageViewModel.RawImageSize)
        state.currentStosConfig.TransformController.SetPoints(transform.points)

        history.SaveState(state.currentStosConfig.TransformController.SetPoints, state.currentStosConfig.TransformController.points)


def AttemptAlignPoint(transform, fixedImage, warpedImage, controlpoint, warpedpoint, alignmentArea, anglesToSearch):
    '''Try to use the Composite view to render the two tiles we need for alignment'''
    FixedRectangle = nornir_imageregistration.Rectangle.CreateFromPointAndArea(point=[controlpoint[0] - (alignmentArea[0] / 2.0),
                                                                                   controlpoint[1] - (alignmentArea[1] / 2.0)],
                                                                             area=alignmentArea)

    FixedRectangle = nornir_imageregistration.Rectangle.SafeRound(FixedRectangle)
    FixedRectangle = nornir_imageregistration.Rectangle.change_area(FixedRectangle, alignmentArea)
    
    # Pull image subregions 
    warpedImageROI = assemble.WarpedImageToFixedSpace(transform,
                            fixedImage.shape, warpedImage, botleft=FixedRectangle.BottomLeft, area=FixedRectangle.Size, extrapolate=True)

    fixedImageROI = nornir_imageregistration.core.CropImage(fixedImage.copy(), FixedRectangle.BottomLeft[1], FixedRectangle.BottomLeft[0], int(FixedRectangle.Size[1]), int(FixedRectangle.Size[0]))

    # nornir_imageregistration.core.ShowGrayscale([fixedImageROI, warpedImageROI])

    # pool = Pools.GetGlobalMultithreadingPool()

    # task = pool.add_task("AttemptAlignPoint", core.FindOffset, fixedImageROI, warpedImageROI, MinOverlap = 0.2)
    # apoint = task.wait_return()
    # apoint = core.FindOffset(fixedImageROI, warpedImageROI, MinOverlap=0.2)
    #nornir_imageregistration.ShowGrayscale([fixedImageROI, warpedImageROI], "Fixed <---> Warped")
 
    apoint = stos.SliceToSliceBruteForce(fixedImageROI, warpedImageROI, AngleSearchRange=anglesToSearch, MinOverlap=0.5, SingleThread=True, Cluster=False, TestFlip=False)

    print("Auto-translate result: " + str(apoint))
    return apoint


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
    
#     if FixedMaskImage:
#         FixedPoints = transform.TransformModel.FixedPoints
#         FixedPointIndicies = numpy.asarray(numpy.round(FixedPoints), dtype=numpy.int32)
#         FixedPointIndiciesOutsideImage = FixedPointIndicies < 0 
#         FixedPointsInMask = FixedMaskImage[FixedPointIndicies]
#         FixedPointsToRemove = FixedPointsInMask == 0
#         transform.TryDeletePoint(FixedPointsToRemove)

    if not WarpedMaskImage is None:
        WarpedPoints = transform.TransformModel.WarpedPoints
        NumPoints = WarpedPoints.shape[0]
        WarpedPointIndicies = numpy.asarray(numpy.floor(WarpedPoints), dtype=numpy.int32)

        OutOfBounds = FindIndiciesOutsideImage(WarpedPointIndicies, WarpedMaskImage)
        
        Indicies =  numpy.asarray(range(0, len(OutOfBounds)), dtype=numpy.int32)
        
        OutOfBoundsIndicies = Indicies[OutOfBounds]
        
        WarpedPointsAndIndex = numpy.hstack((WarpedPoints, numpy.asarray(range(0, NumPoints), dtype=numpy.int32).reshape(NumPoints,1))).astype(numpy.int32)
        
        #transform.RemovePoints(OutOfBounds)
        InBoundsPointsAndIndex = WarpedPointsAndIndex[OutOfBounds==0, :]
        
        WarpedPointsInMask = WarpedMaskImage[InBoundsPointsAndIndex[:,0], InBoundsPointsAndIndex[:,1]]
        WarpedPointsToRemove = WarpedPointsInMask == 0
        MaskedPointIndicies = InBoundsPointsAndIndex[WarpedPointsToRemove,2]
        
        AllMaskedIndicies = numpy.concatenate((OutOfBoundsIndicies, MaskedPointIndicies)) 
        AllMaskedIndicies.sort()
        transform.RemovePoints(AllMaskedIndicies)