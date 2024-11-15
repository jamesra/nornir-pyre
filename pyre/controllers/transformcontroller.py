"""
Created on Oct 19, 2012

@author: u0490822
"""

from __future__ import annotations

import copy
import math
from typing import Callable, Sequence, Iterable

import numpy
import numpy as np
from numpy.typing import NDArray
import wx

import nornir_imageregistration
from nornir_imageregistration import ImagePermutationHelper
from nornir_imageregistration.transforms.base import IControlPoints
import nornir_pools as pools
import pyre.eventmanager
from pyre.interfaces.eventmanager import IEventManager
from pyre.space import Space


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
    # return alignRecord.ToImageTransform(FixedShape,
    # WarpedShape)


TransformChangedCallback = Callable[['transform_controller'], None]

# Parameter order is the transform controller, the old transform, the new transform
TransformModelChangedCallback = Callable[['transform_controller',
                                          nornir_imageregistration.ITransform,
                                          nornir_imageregistration.ITransform], None]


class TransformController:
    """
    Provides methods to edit a transform.  Once passed to a view the controller can replace the transform entirely, but
    the view is not expected to update the transform controller.
    """
    debug_id = 0
    _id: int
    _TransformModel: nornir_imageregistration.ITransform = None
    __OnChangeEventListeners: IEventManager[TransformChangedCallback]
    __OnTransformModelReplacedEventListeners: IEventManager[TransformModelChangedCallback]
    Debug: bool
    ShowWarped: bool
    DefaultToForwardTransform: bool
    _selected_points: set[int] = set()

    @staticmethod
    def swap_columns_to_XY(input: NDArray[np.floating]) -> NDArray[np.floating]:
        """
        OpenGL uses X,Y coordinates.  Everything in Nornir uses Y,X coordinates in numpy arrays.
        For a set of Nx4 control points used by this TransformController this function swaps the
        columns in pairs to obtain the correct X,Y coordinates for rendering.
        """
        output = input[:, [1, 0, 3, 2]]
        return output

    @property
    def selected_points(self) -> set[int]:
        return self._selected_points

    @selected_points.setter
    def selected_points(self, value: set[int]):
        self._selected_points = value

    @property
    def width(self) -> float | None:
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
    def points(self) -> NDArray[np.floating]:
        if isinstance(self.TransformModel, nornir_imageregistration.IControlPoints):
            return copy.deepcopy(self.TransformModel.points)

        return np.empty((0, 4))

    @property
    def SourcePoints(self) -> NDArray[np.floating]:
        if isinstance(self.TransformModel, nornir_imageregistration.IControlPoints):
            return copy.deepcopy(self.TransformModel.SourcePoints)

        return np.empty((0, 2))

    @property
    def TargetPoints(self) -> NDArray[np.floating]:
        if isinstance(self.TransformModel, nornir_imageregistration.IControlPoints):
            return copy.deepcopy(self.TransformModel.TargetPoints)

        return np.empty((0, 2))

    @property
    def WarpedTriangles(self) -> NDArray[np.integer] | None:
        """:return: The triangulation of the source space, or None if the transform does not support triangulation"""
        if isinstance(self._TransformModel, nornir_imageregistration.ITriangulatedSourceSpace):
            return self.TransformModel.source_space_trianglulation
        return None

    @property
    def FixedTriangles(self) -> NDArray[np.integer] | None:
        """:return: The triangulation of the fixed space, or None if the transform does not support triangulation"""
        if isinstance(self._TransformModel, nornir_imageregistration.ITriangulatedTargetSpace):
            return self.TransformModel.target_space_trianglulation
        return None

    @property
    def type(self) -> nornir_imageregistration.transforms.TransformType:
        """Type of transform we are controlling"""
        return self.TransformModel.type

    @property
    def TransformModel(self) -> nornir_imageregistration.ITransform:
        """The transform this controller is editting"""
        return self._TransformModel

    @TransformModel.setter
    def TransformModel(self, value: nornir_imageregistration.ITransform):
        if self._TransformModel == value:
            # No change
            return

        if self._TransformModel is not None:
            self._TransformModel.RemoveOnChangeEventListener(self.OnTransformChanged)

        old_transform = self._TransformModel
        self._TransformModel = value

        if self._TransformModel is not None:
            assert (isinstance(value, nornir_imageregistration.ITransformChangeEvents))
            self._TransformModel.AddOnChangeEventListener(self.OnTransformChanged)

        self.FireOnTransformModelChangeEvent(old_transform, self._TransformModel)
        self.FireOnChangeEvent()

    def Transform(self, points: NDArray[float], **kwargs):
        return self.TransformModel.Transform(points, **kwargs)

    def InverseTransform(self, points: NDArray[float], **kwargs):
        return self.TransformModel.InverseTransform(points, **kwargs)

    def AddOnChangeEventListener(self, func: Callable):
        """Subscribe to be called when the transform changes in a way that a point may be mapped to a new position"""
        self.__OnChangeEventListeners.add(func)

    def RemoveOnChangeEventListener(self, func: Callable):
        """Unsubscribe to be called when the transform changes in a way that a point may be mapped to a new position"""
        self.__OnChangeEventListeners.remove(func)

    def AddOnModelReplacedEventListener(self, func: Callable):
        """Unsubscribe to be called when the entire transform model changes, for example the transform type is changed"""
        self.__OnTransformModelReplacedEventListeners.add(func)

    def RemoveOnModelReplacedEventListener(self, func: Callable):
        """Unsubscribe to be called when the entire transform model changes, for example the transform type is changed"""
        self.__OnTransformModelReplacedEventListeners.remove(func)

    def OnTransformChanged(self):
        # If the transform is getting complicated then use
        # InitializeDataStructures to parallelize the
        # data structure creation as much as possible
        if self.NumPoints > 25:
            self._TransformModel.InitializeDataStructures()
        self.FireOnChangeEvent()

    def FireOnChangeEvent(self):
        """Calls every function registered to be notified when the transform changes."""

        # Calls every listener when the transform has changed in a way that a point may be mapped to a new position in the fixed space
        #        Pool = pools.GetGlobalThreadPool()
        # tlist = list()
        if wx.App.Get() is None:
            self.__OnChangeEventListeners.invoke(self)
        else:
            wx.CallAfter(self.__OnChangeEventListeners.invoke, self)
        #    tlist.append(Pool.add_task("OnTransformChanged calling " + str(func), func))

        # for task in tlist:
        # task.wait()

    def FireOnTransformModelChangeEvent(self, old: nornir_imageregistration.ITransform,
                                        new: nornir_imageregistration.ITransform):
        """Calls every function registered to be notified when the transform changes."""

        # Calls every listener when the transform has changed in a way that a point may be mapped to a new position in the fixed space
        #        Pool = pools.GetGlobalThreadPool()
        # tlist = list()
        if wx.App.Get() is None:
            self.__OnTransformModelReplacedEventListeners.invoke(self, old, new)
        else:
            wx.CallAfter(self.__OnTransformModelReplacedEventListeners.invoke, self, old, new)
        #    tlist.append(Pool.add_task("OnTransformChanged calling " + str(func), func))

        # for task in tlist:
        # task.wait()

    @property
    def Id(self) -> int:
        """Unique ID of this transform controller"""
        return self._id

    def __str__(self):
        return f"TransformController {self.Id} {self.type}"

    def __init__(self, TransformModel: nornir_imageregistration.ITransform | None = None,
                 DefaultToForwardTransform: bool = True):
        """
        Constructor
        """

        self.debug_id = TransformController.debug_id
        self._id = self.debug_id
        TransformController.debug_id += 1

        self.__OnChangeEventListeners = pyre.eventmanager.wxEventManager[TransformChangedCallback]()
        self.__OnTransformModelReplacedEventListeners = pyre.eventmanager.wxEventManager[TransformChangedCallback]()

        self.DefaultToForwardTransform = DefaultToForwardTransform

        self.TransformModel = TransformModel

        if TransformModel is None:
            self.TransformModel = CreateDefaultTransform(nornir_imageregistration.transforms.TransformType.RIGID)

        self.Debug = False
        self.ShowWarped = False

        # print("Create transform controller %d" % self._id)

    def SetPoints(self, points: NDArray | nornir_imageregistration.IControlPoints):
        """Set transform points to the passed array"""
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

        if not self.DefaultToForwardTransform:
            self.ShowWarped = False

    def GetFixedPoint(self, index: int):
        return self.TransformModel.TargetPoints[index, :]

    def GetWarpedPoint(self, index: int):
        return self.TransformModel.SourcePoints[index, :]

    def GetWarpedPointsInRect(self, bounds: nornir_imageregistration.Rectangle):
        return self.TransformModel.GetWarpedPointsInRect(bounds)

    def GetFixedPointsInRect(self, bounds: nornir_imageregistration.Rectangle):
        return self.TransformModel.GetFixedPointsInRect(bounds)

    def NearestPoint(self, ImagePoint: NDArray[np.floating], space: Space) -> tuple[
        float | None, int | None]:
        if isinstance(self.TransformModel, IControlPoints):
            if space == Space.Target:
                return self.TransformModel.NearestWarpedPoint(ImagePoint)
            else:
                return self.TransformModel.NearestFixedPoint(ImagePoint)
        else:
            return None, None

    def TranslateFixed(self, offset: nornir_imageregistration.VectorLike):
        self.TransformModel.TranslateFixed(offset)

    def TranslateWarped(self, offset: nornir_imageregistration.VectorLike):
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
        """
        Flip the target points
        """
        self.TransformModel.FlipWarped()

    def TryAddPoint(self, ImageX: float, ImageY: float, space: Space = Space.Source):

        if not isinstance(self.TransformModel, nornir_imageregistration.transforms.IControlPointAddRemove):
            print("transform does not support add/remove control points")
            return

        OppositePoint = None
        NewPointPair = []
        if space == Space.Target and not self.ShowWarped:
            OppositePoint = self.TransformModel.Transform([[ImageY, ImageX]])
            NewPointPair = [OppositePoint[0][0], OppositePoint[0][1], ImageY, ImageX]
        else:
            OppositePoint = self.TransformModel.InverseTransform([[ImageY, ImageX]])
            NewPointPair = [ImageY, ImageX, OppositePoint[0][0], OppositePoint[0][1]]

        return self.TransformModel.AddPoint(NewPointPair)

    def TryDeletePoint(self, ImageX: float, ImageY: float, maxDistance: float, space: Space = Space.Source):

        if not isinstance(self.TransformModel, nornir_imageregistration.transforms.IControlPointAddRemove):
            print("transform does not support add/remove control points")
            return

        NearestPoint = None
        index = None
        distance = 0

        try:
            if space == Space.Target and not self.ShowWarped:
                distance, index = self.TransformModel.NearestWarpedPoint([ImageY, ImageX])
            else:
                distance, index = self.TransformModel.NearestFixedPoint([ImageY, ImageX])
        except:
            pass;

        if distance > maxDistance:
            return None

        self.TransformModel.RemovePoint(index)
        return True

    def TryDeletePoints(self, indicies: np.ndarray[np.integer] | Sequence[int]):

        if not isinstance(self.TransformModel, nornir_imageregistration.transforms.IControlPointAddRemove):
            print("transform does not support add/remove control points")
            return
        index = self._ensure_numpy_friendly_index(indicies)

        try:
            self.TransformModel.RemovePoint(index)
        except ValueError:
            print(f"Could not remove points {index}, does the transform have enough points remaining?")
            return False

        return True

    def RemovePoints(self, indicies: np.ndarray[np.integer]):
        if isinstance(self.TransformModel, nornir_imageregistration.transforms.IControlPointAddRemove):
            self.TransformModel.RemovePoint(indicies)

    def TryDrag(self, ImageX: float, ImageY: float, ImageDX: float, ImageDY: float, maxDistance: float,
                space: Space = Space.Source):

        NearestPoint = None
        index = None
        Distance = 0

        if not isinstance(self.TransformModel, nornir_imageregistration.IControlPoints):
            return None

        if space == Space.Target and not self.ShowWarped:
            Distance, index = self.TransformModel.NearestWarpedPoint([ImageY, ImageX])
        else:
            Distance, index = self.TransformModel.NearestFixedPoint([ImageY, ImageX])

        if Distance > maxDistance:
            return None

        index = self.MovePoint(index, ImageDY, ImageDX)
        return index

    @staticmethod
    def _ensure_numpy_friendly_index(index: set[int] | NDArray[np.integer] | list[int] | Sequence[int]) -> NDArray[
                                                                                                               int] | int:
        """
        Ensures that the index is a numpy array of integers or an integer
        :param index:
        :return:
        """
        if isinstance(index, int):
            return index
        elif isinstance(index, set):
            index = np.array(list(index), dtype=int)
        elif isinstance(index, list):
            index = np.array(index, dtype=int)
        elif isinstance(index, Sequence):
            index = np.array(index, dtype=int)

        # Convert to an int if we only have one index
        # This is a band-aid as I begin supporting multiple point operations
        if len(index) == 1:
            return int(index[0])

        return index

    def GetPoints(self, index: set[int] | NDArray[np.integer] | list[int], space: Space = Space.Source):
        NearestPoint = None
        index = self._ensure_numpy_friendly_index(index)

        if isinstance(index, Sequence) or isinstance(index, np.ndarray):
            if max(index) > len(self.TransformModel.SourcePoints):
                return None
        else:
            if index > len(self.TransformModel.SourcePoints):
                return None

        if space == Space.Source:
            return self.TransformModel.SourcePoints[index]
        else:
            return self.TransformModel.TargetPoints[index]

    def SetPoint(self, index: int, X: float, Y: float, space: Space = Space.Source) -> int:
        """Sets the specified point to the new location.  If the transform does not support editing the specied space,
        the point is changed in the opposite space if possible.  Raises ValueError if the transform does not support
        editing any space"""
        original_point = np.array((Y, X))
        point = original_point

        index = self._ensure_numpy_friendly_index(index)

        if space == Space.Target:
            if isinstance(self.TransformModel, nornir_imageregistration.transforms.ITargetSpaceControlPointEdit):
                index = self.TransformModel.UpdateTargetPointsByIndex(index, point)
            elif isinstance(self.TransformModel, nornir_imageregistration.transforms.ISourceSpaceControlPointEdit):
                new_source_point = self.TransformModel.InverseTransform([point])[0]
                index = self.TransformModel.UpdateSourcePointsByIndex(index, new_source_point)
            else:
                raise ValueError("Transform does not support editing target points in either source or target space")
        elif space == Space.Source:
            if isinstance(self.TransformModel, nornir_imageregistration.transforms.ISourceSpaceControlPointEdit):
                index = self.TransformModel.UpdateSourcePointsByIndex(index, point)
            elif isinstance(self.TransformModel, nornir_imageregistration.transforms.ITargetSpaceControlPointEdit):
                new_target_point = self.TransformModel.Transform([point])[0]
                index = self.TransformModel.UpdateTargetPointsByIndex(index, new_target_point)
            else:
                raise ValueError("Transform does not support editing target points in either source or target space")
        else:
            raise ValueError(f"Unexpected value for space: {space}")

        print(f"Set point {str(index)} {str(point)}")

        return index

    def MovePoint(self, index: int | list[int], ImageDX: float, ImageDY: float,
                  space: Space = Space.Source) -> int:

        if not isinstance(self.TransformModel, nornir_imageregistration.transforms.IControlPoints):
            return index

        np_index = self._ensure_numpy_friendly_index(index)

        original_point = self.GetPoints(np_index, space)
        if original_point is None:
            print(f"No point found for index {np_index}")
            return index

        point = original_point + numpy.array((ImageDY, ImageDX))

        if space == Space.Source:
            # This code is to manipulate transforms where source space points are fixed.  Instead we move the
            # target points in this case.
            if not isinstance(self.TransformModel, nornir_imageregistration.transforms.ISourceSpaceControlPointEdit):
                # if not self.ShowWarped:
                #     np_index = self.TransformModel.UpdateSourcePointsByPosition(original_point, point)
                # else:
                if isinstance(index, Iterable):
                    if len(index) > 1:
                        raise NotImplementedError("MovePoint does not support moving multiple points, but it should")

                OldWarpedPoint = \
                    self.TransformModel.InverseTransform([[point[0] - ImageDY, point[1] - ImageDX]])[0]
                NewWarpedPoint = self.TransformModel.InverseTransform([point])[0]

                TranslatedPoint = NewWarpedPoint - OldWarpedPoint

                FinalPoint = self.TransformModel.SourcePoints[np_index] + TranslatedPoint
                np_index = self.TransformModel.UpdateTargetPointsByIndex(np_index, FinalPoint)
            else:
                np_index = self.TransformModel.UpdateSourcePointsByIndex(np_index, point)
        else:
            if isinstance(self.TransformModel, nornir_imageregistration.transforms.ITargetSpaceControlPointEdit):
                np_index = self.TransformModel.UpdateTargetPointsByIndex(np_index, point)

        # print(f'Dragged point {str(np_index)} {str(point)}')

        if isinstance(index, Iterable) and not isinstance(np_index, Iterable):
            return np.array([np_index], dtype=int)
        else:
            return np_index
