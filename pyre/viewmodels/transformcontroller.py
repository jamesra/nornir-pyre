'''
Created on Oct 19, 2012

@author: u0490822
'''

import copy
import logging
import math
import time

import nornir_imageregistration
import numpy
from numpy.typing import NDArray
import pyglet
from pyglet.gl import *
import scipy.ndimage
import scipy.spatial

import pyre
import nornir_pools as pools
import numpy as np
from nornir_imageregistration.transforms.base import IControlPoints
from numpy.distutils.fcompiler import none


def CreateDefaultTransform(transform_type: nornir_imageregistration.transforms.TransformType,
                           FixedShape: NDArray | None = None,
                           WarpedShape: NDArray | None = None):
    if transform_type == nornir_imageregistration.transforms.TransformType.RIGID:
        return CreateDefaultRigidTransform(FixedShape, WarpedShape)
    elif transform_type == nornir_imageregistration.transforms.TransformType.MESH:
        return CreateDefaultMeshTransform(FixedShape, WarpedShape)
    elif transform_type == nornir_imageregistration.transforms.TransformType.GRID:
        return CreateDefaultMeshTransform(FixedShape, WarpedShape)

    raise NotImplemented()


def CreateDefaultRigidTransform(FixedShape=None, WarpedShape=None):
    return nornir_imageregistration.transforms.CenteredSimilarity2DTransform(target_offset=(0, 0),
                                                                             source_rotation_center=(0, 0), angle=0,
                                                                             scalar=1)


def CreateDefaultMeshTransform(FixedShape=None, WarpedShape=None):
    # FixedSize = Utils.Images.GetImageSize(FixedImageFullPath)
    # WarpedSize = Utils.Images.GetImageSize(WarpedImageFullPath)

    if FixedShape is None:
        FixedShape = (512, 512)

    if WarpedShape is None:
        WarpedShape = (512, 512)

    return nornir_imageregistration.transforms.factory.CreateRigidMeshTransform(target_image_shape=FixedShape,
                                                                                source_image_shape=WarpedShape,
                                                                                rangle=0.0,
                                                                                warped_offset=(0, 0),
                                                                                flip_ud=False,
                                                                                scale=1.0)

    # alignRecord = nornir_imageregistration.AlignmentRecord(peak=(0, 0), weight=0, angle=0)
    # return alignRecord.ToTransform(FixedShape,
    # WarpedShape)


class TransformController(object):
    '''
    Combines an image and a transform to render an image
    '''
    debug_id = 0

    @staticmethod
    def CreateDefault(FixedShape=None, WarpedShape=None):
        T = CreateDefaultTransform(nornir_imageregistration.transforms.TransformType.RIGID, FixedShape, WarpedShape)
        return TransformController(T)

    @property
    def width(self):
        if isinstance(self.TransformModel, nornir_imageregistration.IDiscreteTransform):
            return self.TransformModel.FixedBoundingBox.Width

        return None

    @property
    def height(self) -> float | None:
        if isinstance(self.TransformModel, nornir_imageregistration.IDiscreteTransform):
            return self.TransformModel.FixedBoundingBox.Height

        return None

    @property
    def NumPoints(self) -> int:
        if isinstance(self.TransformModel, nornir_imageregistration.IControlPoints):
            return self.TransformModel.points.shape[0]

        return 0

    @property
    def points(self):
        if isinstance(self.TransformModel, nornir_imageregistration.IControlPoints):
            return copy.deepcopy(self.TransformModel.points)

        return ()

    @property
    def SourcePoints(self):
        if isinstance(self.TransformModel, nornir_imageregistration.IControlPoints):
            return copy.deepcopy(self.TransformModel.SourcePoints)

        return ()

    @property
    def TargetPoints(self):
        if isinstance(self.TransformModel, nornir_imageregistration.IControlPoints):
            return copy.deepcopy(self.TransformModel.TargetPoints)

        return ()

    @property
    def WarpedTriangles(self):
        return self.TransformModel.WarpedTriangles

    @property
    def FixedTriangles(self):
        return self.TransformModel.FixedTriangles

    @property
    def TransformModel(self) -> nornir_imageregistration.ITransform:
        return self._TransformModel

    @TransformModel.setter
    def TransformModel(self, value: nornir_imageregistration.ITransform):

        if self._TransformModel is not None:
            self._TransformModel.RemoveOnChangeEventListener(self.OnTransformChanged)

        self._TransformModel = value

        if value is not None:
            assert (isinstance(value, nornir_imageregistration.ITransformChangeEvents))
            self._TransformModel.AddOnChangeEventListener(self.OnTransformChanged)

        self.FireOnChangeEvent()

    def Transform(self, points: NDArray[float], **kwargs):
        return self.TransformModel.Transform(points, **kwargs)

    def InverseTransform(self, points: NDArray[float], **kwargs):
        return self.TransformModel.InverseTransform(points, **kwargs)

    def AddOnChangeEventListener(self, func):
        self.__OnChangeEventListeners.append(func)

    def RemoveOnChangeEventListener(self, func):
        if func in self.__OnChangeEventListeners:
            self.__OnChangeEventListeners.remove(func)

    def OnTransformChanged(self):
        # If the transform is getting complicated then use InitializeDataStructures to parallelize the
        # data structure creation as much as possible
        if self.NumPoints > 25:
            self._TransformModel.InitializeDataStructures()
        self.FireOnChangeEvent()

    def FireOnChangeEvent(self):
        '''Calls every function registered to be notified when the transform changes.'''

        # Calls every listener when the transform has changed in a way that a point may be mapped to a new position in the fixed space
        #        Pool = pools.GetGlobalThreadPool()
        # tlist = list()
        for func in self.__OnChangeEventListeners:
            func()
        #    tlist.append(Pool.add_task("OnTransformChanged calling " + str(func), func))

        # for task in tlist:
        # task.wait()

    def __init__(self, TransformModel: nornir_imageregistration.ITransform | None = None,
                 DefaultToForwardTransform: bool = True):
        '''
        Constructor
        '''

        self.debug_id
        self._id = self.debug_id
        self.debug_id += 1

        self.__OnChangeEventListeners = []
        self._TransformModel = None

        self.DefaultToForwardTransform = DefaultToForwardTransform

        self.TransformModel = TransformModel

        if TransformModel is None:
            self.TransformModel = CreateDefaultTransform()

        self.Debug = False
        self.ShowWarped = False

        # print("Create transform controller %d" % self._id)

    def SetPoints(self, points: NDArray | nornir_imageregistration.IControlPoints):
        '''Set transform points to the passed array'''
        if isinstance(points, nornir_imageregistration.IControlPoints):
            points = points.points
        elif isinstance(points, np.ndarray):
            pass
        else:
            raise ValueError(f"points parameter has unexpected type: {points.__class__}")

        if isinstance(self.TransformModel, IControlPoints):
            self.TransformModel.points = points

        return

    def NextViewMode(self):
        self.ShowWarped = not self.ShowWarped

        if self.DefaultToForwardTransform == False:
            self.ShowWarped = False

    def GetFixedPoint(self, index):
        return self.TransformModel.TargetPoints[index, :]

    def GetWarpedPoint(self, index):
        return self.TransformModel.SourcePoints[index, :]

    def GetWarpedPointsInRect(self, bounds):
        return self.TransformModel.GetWarpedPointsInRect(bounds)

    def GetFixedPointsInRect(self, bounds):
        return self.TransformModel.GetFixedPointsInRect(bounds)

    def NearestPoint(self, ImagePoint, FixedSpace=True) -> tuple[float, int]:
        if isinstance(self.TransformModel, IControlPoints):
            if FixedSpace is False:
                return self.TransformModel.NearestWarpedPoint(ImagePoint)
            else:
                return self.TransformModel.NearestFixedPoint(ImagePoint)
        else:
            return None, None

    def TranslateFixed(self, offset):
        self.TransformModel.TranslateFixed(offset)

    def TranslateWarped(self, offset):
        self.TransformModel.TranslateWarped(offset)

    def Rotate(self, rangle: float, center: NDArray[float] | None = None):
        if isinstance(self._TransformModel, nornir_imageregistration.ITransformTargetRotation):
            self.TransformModel.RotateTargetPoints(-rangle, center)
            self.FireOnChangeEvent()
        elif isinstance(self._TransformModel, nornir_imageregistration.ITransformSourceRotation):
            self.TransformModel.RotateSourcePoints(rangle, center)
            self.FireOnChangeEvent()
        else:
            raise NotImplementedError("Current transform does not support rotation")

    def FlipWarped(self):
        '''
        Flip the target points 
        '''
        self.TransformModel.FlipWarped()

    def TryAddPoint(self, ImageX, ImageY, FixedSpace=True):

        if not isinstance(self.TransformModel, nornir_imageregistration.transforms.IControlPointAddRemove):
            print("Transform does not support add/remove control points")
            return

        OppositePoint = None
        NewPointPair = []
        if not FixedSpace and not self.ShowWarped:
            OppositePoint = self.TransformModel.Transform([[ImageY, ImageX]])
            NewPointPair = [OppositePoint[0][0], OppositePoint[0][1], ImageY, ImageX]
        else:
            OppositePoint = self.TransformModel.InverseTransform([[ImageY, ImageX]])
            NewPointPair = [ImageY, ImageX, OppositePoint[0][0], OppositePoint[0][1]]

        return self.TransformModel.AddPoint(NewPointPair)

    def TryDeletePoint(self, ImageX, ImageY, maxDistance, FixedSpace=True):

        if not isinstance(self.TransformModel, nornir_imageregistration.transforms.IControlPointAddRemove):
            print("Transform does not support add/remove control points")
            return

        NearestPoint = None
        index = None
        distance = 0

        try:
            if not FixedSpace and not self.ShowWarped:
                distance, index = self.TransformModel.NearestWarpedPoint([ImageY, ImageX])
            else:
                distance, index = self.TransformModel.NearestFixedPoint([ImageY, ImageX])
        except:
            pass;

        if distance > maxDistance:
            return None

        self.TransformModel.RemovePoint(index)
        return True

    def RemovePoints(self, indicies):
        if isinstance(self.TransformModel, nornir_imageregistration.transforms.IControlPointAddRemove):
            self.TransformModel.RemovePoint(indicies)

    def TryDrag(self, ImageX, ImageY, ImageDX, ImageDY, maxDistance, FixedSpace=True):

        NearestPoint = None
        index = None
        Distance = 0

        if not isinstance(self.TransformModel, nornir_imageregistration.IControlPoints):
            return None

        if not FixedSpace and not self.ShowWarped:
            Distance, index = self.TransformModel.NearestWarpedPoint([ImageY, ImageX])
        else:
            Distance, index = self.TransformModel.NearestFixedPoint([ImageY, ImageX])

        if Distance > maxDistance:
            return None

        index = self.MovePoint(index, ImageDY, ImageDX)
        return index

    def GetNearestPoint(self, index: int, FixedSpace: bool = False):
        NearestPoint = None
        if index > len(self.TransformModel.SourcePoints):
            return None

        if not FixedSpace and not self.ShowWarped:
            NearestPoint = copy.copy(self.TransformModel.SourcePoints[index])
        else:
            NearestPoint = copy.copy(self.TransformModel.TargetPoints[index])

        return NearestPoint

    def SetPoint(self, index: int, X, Y, FixedSpace: bool = True) -> int:
        original_point = np.array((Y, X))
        point = original_point

        if not FixedSpace:
            if isinstance(self.TransformModel, nornir_imageregistration.transforms.ISourceSpaceControlPointEdit):
                if not self.ShowWarped:
                    index = self.TransformModel.UpdateSourcePointsByPosition(original_point, point)
                else:
                    NewWarpedPoint = self.TransformModel.InverseTransform([point])[0]
                    index = self.TransformModel.UpdateSourcePointsByPosition(original_point, NewWarpedPoint)
        else:
            if isinstance(self.TransformModel, nornir_imageregistration.transforms.ITargetSpaceControlPointEdit):
                index = self.TransformModel.UpdateTargetPointsByPosition(original_point, point)

        print(f"Set point {str(index)} {str(point)}")

        return index

    def MovePoint(self, index: int, ImageDX, ImageDY, FixedSpace: bool = True) -> int:

        if not isinstance(self.TransformModel, nornir_imageregistration.transforms.IControlPoints):
            return

        original_point = self.GetNearestPoint(index, FixedSpace)
        if original_point is None:
            print(f"No point found for index {index}")
            return

        point = original_point + numpy.array((ImageDY, ImageDX))

        if not FixedSpace:
            if isinstance(self.TransformModel, nornir_imageregistration.transforms.ISourceSpaceControlPointEdit):
                if not self.ShowWarped:
                    index = self.TransformModel.UpdateSourcePointsByPosition(original_point, point)
                else:
                    OldWarpedPoint = \
                        self.TransformModel.InverseTransform([[point[0] - ImageDY, point[1] - ImageDX]])[0]
                    NewWarpedPoint = self.TransformModel.InverseTransform([point])[0]

                    TranslatedPoint = NewWarpedPoint - OldWarpedPoint

                    FinalPoint = self.TransformModel.SourcePoints[index] + TranslatedPoint
                    index = self.TransformModel.UpdateSourcePointsByPosition(original_point, FinalPoint)
        else:
            if isinstance(self.TransformModel, nornir_imageregistration.transforms.ITargetSpaceControlPointEdit):
                index = self.TransformModel.UpdateTargetPointsByPosition(original_point, point)

        print(f'Dragged point {str(index)} {str(point)}')

        return index

    def AutoAlignPoints(self, i_points):
        '''Attemps to align the specified point indicies'''
        from pyre.state import currentStosConfig

        if (currentStosConfig.FixedImageViewModel is None or
                currentStosConfig.WarpedImageViewModel is None):
            return

        if isinstance(i_points, range):
            i_points = list(i_points)

        if not isinstance(i_points, list):
            i_points = [i_points]

        offsets = np.zeros((self.NumPoints, 2))

        indextotask = {}
        invalid_points = []
        if len(i_points) > 1:
            pool = pools.GetGlobalLocalMachinePool()

            for i_point in i_points:
                fixed = self.GetFixedPoint(i_point)
                warped = self.GetWarpedPoint(i_point)

                task = pyre.common.StartAttemptAlignPoint(pool=pool,
                                                          task_description=f"Align Pyre Point {i_point}",
                                                          transform=self.TransformModel,
                                                          target_image=currentStosConfig.FixedImages.ImageWithMaskAsNoise,
                                                          source_image=currentStosConfig.WarpedImages.ImageWithMaskAsNoise,
                                                          target_mask=currentStosConfig.FixedImages.BlendedMask,
                                                          source_mask=currentStosConfig.WarpedImages.BlendedMask,
                                                          target_image_stats=currentStosConfig.FixedImageViewModel.Stats,
                                                          source_image_stats=currentStosConfig.WarpedImageViewModel.Stats,
                                                          target_controlpoint=fixed,
                                                          alignmentArea=currentStosConfig.AlignmentTileSize,
                                                          anglesToSearch=currentStosConfig.AnglesToSearch)

                if task is not None:
                    indextotask[i_point] = task
                else:
                    invalid_points.append(i_point)

            for i_point in sorted(indextotask.keys()):
                task = indextotask[i_point]

                record = None
                try:
                    record = task.wait_return()
                except Exception as e:
                    print(f"Exception aligning point {i_point}:\n{e}")
                    return

                if record is None:
                    print("point #" + str(i_point) + " returned None for alignment")
                    continue

                if record.weight == 0:
                    print("point #" + str(i_point) + " returned weight 0 for alignment, ignoring")
                    continue

                (dy, dx) = record.peak

                if math.isnan(dx) or math.isnan(dy):
                    continue

                offsets[i_point, :] = np.array([dy, dx])
                del indextotask[i_point]

        else:
            i_point = i_points[0]
            fixed = self.GetFixedPoint(i_point)
            warped = self.GetWarpedPoint(i_point)
            task = pyre.common.StartAttemptAlignPoint(pool=pools.GetGlobalLocalMachinePool(),
                                                      task_description=f"Align Pyre Point {i_point}",
                                                      transform=self.TransformModel,
                                                      target_image=currentStosConfig.FixedImages.ImageWithMaskAsNoise,
                                                      source_image=currentStosConfig.WarpedImages.ImageWithMaskAsNoise,
                                                      target_mask=currentStosConfig.FixedImages.BlendedMask,
                                                      source_mask=currentStosConfig.WarpedImages.BlendedMask,
                                                      target_image_stats=currentStosConfig.FixedImageViewModel.Stats,
                                                      source_image_stats=currentStosConfig.WarpedImageViewModel.Stats,
                                                       target_controlpoint=fixed,
                                                      alignmentArea=currentStosConfig.AlignmentTileSize,
                                                      anglesToSearch=currentStosConfig.AnglesToSearch)

            if task is None:
                print("point #" + str(i_point) + " had no texture for alignment")
                return

            record = None
            try:
                record = task.wait_return()
            except Exception as e:
                print(f"Exception aligning point {i_point}:\n{e}")
                return

            if record is None:
                print("point #" + str(i_point) + " returned None for alignment")
                return

            if record.weight == 0:
                print("point #" + str(i_point) + " returned weight 0 for alignment, ignoring")
                return

            (dy, dx) = record.peak

            if math.isnan(dx) or math.isnan(dy):
                return

            print(f"Adjusting point {i_point} by x: {dx} y: {dy}")
            offsets[i_point, :] = np.array([dy, dx])

        # Translate all points
        self.TranslateFixed(offsets)

        # If we aligned all points, remove the ones we couldn't register
        self.RemovePoints(invalid_points)

        # return self.TransformController.MovePoint(i_point, dx, dy, FixedSpace = self.FixedSpace)
