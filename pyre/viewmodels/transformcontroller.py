'''
Created on Oct 19, 2012

@author: u0490822
'''

import copy
import logging
import math
import time

from nornir_imageregistration.alignment_record import AlignmentRecord
from nornir_imageregistration.transforms import *
import numpy
import pyglet
from pyglet.gl import *
import scipy.ndimage
import scipy.spatial

import pyre.common
import nornir_pools as pools
import numpy as np


def CreateDefaultTransform(FixedShape=None, WarpedShape=None):
    # FixedSize = Utils.Images.GetImageS ize(FixedImageFullPath)
    # WarpedSize = Utils.Images.GetImageSize(WarpedImageFullPath)
 
    if FixedShape is None:
        FixedShape = (512, 512)

    if WarpedShape is None:
        WarpedShape = (512, 512)

    alignRecord = AlignmentRecord(peak=(0, 0), weight=0, angle=0)
    return alignRecord.ToTransform(FixedShape,
                                        WarpedShape)


debugid = 0


class  TransformController(object):
    '''
    Combines an image and a transform to render an image
    '''

    @classmethod
    def CreateDefault(cls, FixedShape=None, WarpedShape=None):
        T = CreateDefaultTransform(FixedShape, WarpedShape)
        return TransformController(T)

    @property
    def width(self):
        return self.TransformModel.FixedBoundingBox.Width
 
    @property
    def height(self):
        return self.TransformModel.FixedBoundingBox.Height

    @property
    def NumPoints(self):
        return self.TransformModel.points.shape[0]
 
    @property
    def points(self):
        return copy.deepcopy(self.TransformModel.points)

    @property
    def SourcePoints(self):
        return copy.deepcopy(self.TransformModel.SourcePoints)

    @property
    def TargetPoints(self):
        return copy.deepcopy(self.TransformModel.TargetPoints)

    @property
    def WarpedTriangles(self):
        return self.TransformModel.WarpedTriangles

    @property
    def FixedTriangles(self):
        return self.TransformModel.FixedTriangles

    @property
    def TransformModel(self):
        return self._TransformModel;

    @TransformModel.setter
    def TransformModel(self, value):

        if not self._TransformModel is None:
            self._TransformModel.RemoveOnChangeEventListener(self.OnTransformChanged)

        self._TransformModel = value;

        if not value is None:
            assert(isinstance(value, triangulation.Triangulation))
            self._TransformModel.AddOnChangeEventListener(self.OnTransformChanged)

    def Transform(self, points, **kwargs):
        return self.TransformModel.Transform(points, **kwargs)

    def InverseTransform(self, points, **kwargs):
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

    def __init__(self, TransformModel=None, DefaultToForwardTransform=True):
        '''
        Constructor
        '''
        
        global debugid
        self._id = debugid
        debugid += 1
        
        self.__OnChangeEventListeners = []
        self._TransformModel = None

        self.DefaultToForwardTransform = DefaultToForwardTransform;

        self.TransformModel = TransformModel

        if TransformModel is None:
            self.TransformModel = CreateDefaultTransform()

        self.Debug = False;
        self.ShowWarped = False;
        
        # print("Create transform controller %d" % self._id)

    def SetPoints(self, points):
        '''Set transform points to the passed array'''
        self.TransformModel.points = points

    def NextViewMode(self):
        self.ShowWarped = not self.ShowWarped;

        if self.DefaultToForwardTransform == False:
            self.ShowWarped = False;

    def GetFixedPoint(self, index):
        return self.TransformModel.TargetPoints[index];

    def GetWarpedPoint(self, index):
        return self.TransformModel.SourcePoints[index];

    def GetWarpedPointsInRect(self, bounds):
        return self.TransformModel.GetWarpedPointsInRect(bounds)

    def GetFixedPointsInRect(self, bounds):
        return self.TransformModel.GetFixedPointsInRect(bounds)

    def NearestPoint(self, ImagePoint, FixedSpace=True):
        if(not FixedSpace):
            Distance, index = self.TransformModel.NearestWarpedPoint(ImagePoint);
        else:
            Distance, index = self.TransformModel.NearestFixedPoint(ImagePoint);

        return (Distance, index);

    def TranslateFixed(self, offset):
        self.TransformModel.TranslateFixed(offset)

    def TranslateWarped(self, offset):
        self.TransformModel.TranslateWarped(offset)

    def RotateWarped(self, angle, center):
        self.TransformModel.RotateWarped(angle, center)
        
    def FlipWarped(self):
        '''
        Flip the target points 
        '''
        self.TransformModel.FlipWarped()

    def TryAddPoint(self, ImageX, ImageY, FixedSpace=True):

        OppositePoint = None;
        NewPointPair = [];
        if(not FixedSpace and not self.ShowWarped):
            OppositePoint = self.TransformModel.Transform([[ImageY, ImageX]]);
            NewPointPair = [OppositePoint[0][0], OppositePoint[0][1], ImageY, ImageX];
        else:
            OppositePoint = self.TransformModel.InverseTransform([[ImageY, ImageX]]);
            NewPointPair = [ImageY, ImageX, OppositePoint[0][0], OppositePoint[0][1]];

        return self.TransformModel.AddPoint(NewPointPair);

    def TryDeletePoint(self, ImageX, ImageY, maxDistance, FixedSpace=True):

        NearestPoint = None;
        index = None;
        Distance = 0;

        try:
            if(not FixedSpace and not self.ShowWarped):
                Distance, index = self.TransformModel.NearestWarpedPoint([ImageY, ImageX]);
            else:
                Distance, index = self.TransformModel.NearestFixedPoint([ImageY, ImageX]);
        except:
            pass;

        if(Distance > maxDistance):
            return None;

        self.TransformModel.RemovePoint(index);
        return True;
    
    def RemovePoints(self, indicies):
        self.TransformModel.RemovePoint(indicies)
        
        
    def TryDrag(self, ImageX, ImageY, ImageDX, ImageDY, maxDistance, FixedSpace=True):

        NearestPoint = None;
        index = None;
        Distance = 0;
        if(not FixedSpace  and not self.ShowWarped):
            Distance, index = self.TransformModel.NearestWarpedPoint([ImageY, ImageX]);
        else:
            Distance, index = self.TransformModel.NearestFixedPoint([ImageY, ImageX]);

        if(Distance > maxDistance):
            return None;

        index = self.MovePoint(index, ImageDY, ImageDX);
        return index;

    def GetNearestPoint(self, index, FixedSpace=False):
        NearestPoint = None
        if index > len(self.TransformModel.SourcePoints):
            return None
        
        if(not FixedSpace  and not self.ShowWarped):
            NearestPoint = copy.copy(self.TransformModel.SourcePoints[index])
        else:
            NearestPoint = copy.copy(self.TransformModel.TargetPoints[index])

        return NearestPoint

    def SetPoint(self, index, X, Y, FixedSpace=True):
        OldPointPosition = self.GetNearestPoint(index, FixedSpace)

        NewPointPosition = (Y, X)

        if(not FixedSpace):
            if not self.ShowWarped:
                index = self.TransformModel.UpdateWarpedPoint(index, NewPointPosition);
            else:
                NewWarpedPoint = self.TransformModel.InverseTransform([NewPointPosition])[0];
                index = self.TransformModel.UpdateWarpedPoint(index, NewWarpedPoint);
        else:
            index = self.TransformModel.UpdateFixedPoint(index, NewPointPosition);

        print("Set point " + str(index) + " " + str(NewPointPosition))

        return index;

    def MovePoint(self, index, ImageDX, ImageDY, FixedSpace=True):

        NearestPoint = self.GetNearestPoint(index, FixedSpace)

        NearestPoint += numpy.array((ImageDY, ImageDX))
        # NearestPoint[0] = NearestPoint[0] + ImageDY;
        # NearestPoint[1] = NearestPoint[1] + ImageDX;

        if(not FixedSpace):
            if not self.ShowWarped:
                index = self.TransformModel.UpdateWarpedPoint(index, NearestPoint);
            else:
                OldWarpedPoint = self.TransformModel.InverseTransform([[NearestPoint[0] - ImageDY, NearestPoint[1] - ImageDX]])[0];
                NewWarpedPoint = self.TransformModel.InverseTransform([NearestPoint])[0];

                TranslatedPoint = NewWarpedPoint - OldWarpedPoint 

                FinalPoint = self.TransformModel.SourcePoints[index] + TranslatedPoint 
                index = self.TransformModel.UpdateWarpedPoint(index, FinalPoint);
        else:
            index = self.TransformModel.UpdateFixedPoint(index, NearestPoint);

        print("Dragged point " + str(index) + " " + str(NearestPoint))

        return index;

    def AutoAlignPoints(self, i_points):
        '''Attemps to align the specified point indicies'''
        from pyre.state import currentStosConfig

        if(currentStosConfig.FixedImageViewModel is None or
           currentStosConfig.WarpedImageViewModel is None):
            return

        if not isinstance(i_points, list):
            i_points = [i_points]
            
        offsets = np.zeros((self.NumPoints, 2))

        indextotask = {}
        if len(i_points) > 1:
            pool = pools.GetGlobalLocalMachinePool()
            
            for i_point in i_points:
                fixed = self.GetFixedPoint(i_point)
                warped = self.GetWarpedPoint(i_point)
                
                task = pool.add_task(i_point, pyre.common.AttemptAlignPoint,
                                                self,
                                                currentStosConfig.FixedImageViewModel.Image,
                                                currentStosConfig.WarpedImageViewModel.Image,
                                                fixed,
                                                alignmentArea=currentStosConfig.AlignmentTileSize,
                                                anglesToSearch=currentStosConfig.AnglesToSearch)
                indextotask[i_point] = task       
    
            for i_point in sorted(indextotask.keys()):
                task = indextotask[i_point]
                record = task.wait_return()
    
                if record is None:
                    print("point #" + str(i_point) + " returned None for alignment")
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
            record = pyre.common.AttemptAlignPoint(self,
                                    currentStosConfig.FixedImageViewModel.Image,
                                    currentStosConfig.WarpedImageViewModel.Image,
                                    fixed,
                                    alignmentArea=currentStosConfig.AlignmentTileSize,
                                    anglesToSearch=currentStosConfig.AnglesToSearch)
            
            if record is None:
                print("point #" + str(i_point) + " returned None for alignment")
                return

            (dy, dx) = record.peak

            if math.isnan(dx) or math.isnan(dy):
                return

            offsets[i_point, :] = np.array([dy, dx])
            
        # Translate all points
        self.TranslateFixed(offsets)

        # return self.TransformController.MovePoint(i_point, dx, dy, FixedSpace = self.FixedSpace)
