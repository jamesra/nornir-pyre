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
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

import nornir_imageregistration
from nornir_imageregistration import ImagePermutationHelper
from nornir_imageregistration.transforms.base import IControlPoints
import nornir_imageregistration.interactive_edit
import nornir_pools as pools
import pyre.qt_eventmanager
from pyre.controllers.tile_mesh_cache import TileMeshCpuCache
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

    raise NotImplementedError()


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


TransformChangedCallback = Callable[['TransformController'], None]

# Called during interactive edit (point drag) with the indices that moved.
PointMovedCallback = Callable[['TransformController', NDArray[np.integer]], None]

# Parameter order is the transform controller, the old transform, the new transform
TransformModelChangedCallback = Callable[['TransformController',
                                          nornir_imageregistration.ITransform,
                                          nornir_imageregistration.ITransform], None]


class TransformController:
    """
    Provides methods to edit a transform.  Once passed to a view the controller can replace the transform entirely, but
    the view is not expected to update the transform controller.
    """
    debug_id = 0
    _id: int
    _TransformModel: nornir_imageregistration.ITransform | None = None
    __OnChangeEventListeners: IEventManager[TransformChangedCallback]
    __OnTransformModelReplacedEventListeners: IEventManager[TransformModelChangedCallback]
    Debug: bool
    ShowWarped: bool
    DefaultToForwardTransform: bool
    _selected_points: set[int] = set()
    _change_event_pending: bool = False  # True while a coalesced OnChange notification is queued
    _point_moved_event_pending: bool = False
    _interactive_edit_depth: int = 0
    _interactive_edit_space: Space | None = None
    _rigid_matrix_at_edit_start: NDArray[np.floating] | None = None
    _rigid_inverse_matrix_at_edit_start: NDArray[np.floating] | None = None
    _pending_moved_indices: set[int]
    _tile_mesh_cache: TileMeshCpuCache
    _full_refresh_needed: bool = False

    @property
    def interactive_edit_in_progress(self) -> bool:
        """True while a command is performing continuous transform edits (e.g. point drag)."""
        return self._interactive_edit_depth > 0

    @property
    def tile_mesh_cache(self) -> TileMeshCpuCache:
        return self._tile_mesh_cache

    @property
    def interactive_edit_space(self) -> Space | None:
        """Which display space is being edited during an interactive drag (Source=fixed, Target=warped)."""
        return self._interactive_edit_space

    @property
    def rigid_matrix_at_edit_start(self) -> NDArray[np.floating] | None:
        return self._rigid_matrix_at_edit_start

    @property
    def rigid_inverse_matrix_at_edit_start(self) -> NDArray[np.floating] | None:
        return self._rigid_inverse_matrix_at_edit_start

    def begin_interactive_edit(self, space: Space | None = None) -> None:
        """Mark the start of a continuous edit. Heavy display refresh is deferred until end."""
        if self._interactive_edit_depth == 0:
            self._interactive_edit_space = space
            if isinstance(self._TransformModel, nornir_imageregistration.IRigidTransform):
                from pyre.gl_engine.shaders.texture_shader import TextureShader
                fwd, inv = TextureShader.rigid_matrices_from_transform(self._TransformModel)
                self._rigid_matrix_at_edit_start = fwd
                self._rigid_inverse_matrix_at_edit_start = inv
        self._interactive_edit_depth += 1
        nornir_imageregistration.interactive_edit.begin()
        self._pending_moved_indices.clear()

    def end_interactive_edit(self) -> None:
        """End continuous edit and run any deferred full refresh."""
        if self._interactive_edit_depth > 0:
            self._interactive_edit_depth -= 1
        nornir_imageregistration.interactive_edit.end()
        if self._interactive_edit_depth == 0:
            self._interactive_edit_space = None
            self._rigid_matrix_at_edit_start = None
            self._rigid_inverse_matrix_at_edit_start = None
            if self._full_refresh_needed:
                self._full_refresh_needed = False
                self._run_post_interactive_refresh()

    def _run_post_interactive_refresh(self) -> None:
        if self.NumPoints > 25 and hasattr(self._TransformModel, 'InitializeDataStructures'):
            self._TransformModel.InitializeDataStructures()  # type: ignore[union-attr]
        self._tile_mesh_cache.clear()
        self.FireOnChangeEvent()

    def copy_points(self) -> NDArray[np.floating]:
        """Return a deep copy of control points (for undo/command snapshots)."""
        if isinstance(self.TransformModel, nornir_imageregistration.IControlPoints):
            return copy.deepcopy(self.TransformModel.points)
        return np.empty((0, 4))

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
            return np.asarray(self.TransformModel.points)

        return np.empty((0, 4))

    @property
    def SourcePoints(self) -> NDArray[np.floating]:
        if isinstance(self.TransformModel, nornir_imageregistration.IControlPoints):
            return np.asarray(self.TransformModel.SourcePoints)

        return np.empty((0, 2))

    @property
    def TargetPoints(self) -> NDArray[np.floating]:
        if isinstance(self.TransformModel, nornir_imageregistration.IControlPoints):
            return np.asarray(self.TransformModel.TargetPoints)

        return np.empty((0, 2))

    @property
    def WarpedTriangles(self) -> NDArray[np.integer] | None:
        """:return: The triangulation of the source space, or None if the transform does not support triangulation"""
        if isinstance(self._TransformModel, nornir_imageregistration.ITriangulatedSourceSpace):
            return self._TransformModel.source_space_trianglulation  # type: ignore[attr-defined]
        return None

    @property
    def FixedTriangles(self) -> NDArray[np.integer] | None:
        """:return: The triangulation of the fixed space, or None if the transform does not support triangulation"""
        if isinstance(self._TransformModel, nornir_imageregistration.ITriangulatedTargetSpace):
            return self._TransformModel.target_space_trianglulation  # type: ignore[attr-defined]
        return None

    @property
    def type(self) -> nornir_imageregistration.transforms.TransformType:
        """Type of transform we are controlling"""
        return self.TransformModel.type

    @property
    def TransformModel(self) -> nornir_imageregistration.ITransform:
        """The transform this controller is editing"""
        return self._TransformModel  # type: ignore[return-value]

    @TransformModel.setter
    def TransformModel(self, value: nornir_imageregistration.ITransform | None):
        if self._TransformModel == value:
            # No change
            return

        if self._TransformModel is not None:
            self._TransformModel.RemoveOnChangeEventListener(self.OnTransformChanged)  # type: ignore[union-attr]

        old_transform = self._TransformModel
        self._TransformModel = value

        if self._TransformModel is not None:
            assert (isinstance(value, nornir_imageregistration.ITransformChangeEvents))
            self._TransformModel.AddOnChangeEventListener(self.OnTransformChanged)  # type: ignore[union-attr]

        self.FireOnTransformModelChangeEvent(old_transform, self._TransformModel)  # type: ignore[arg-type]
        self.FireOnChangeEvent()

    def Transform(self, points: NDArray[np.floating], **kwargs):
        return self.TransformModel.Transform(points, **kwargs)

    def InverseTransform(self, points: NDArray[np.floating], **kwargs):
        return self.TransformModel.InverseTransform(points, **kwargs)

    def AddOnChangeEventListener(self, func: Callable):
        """Subscribe to be called when the transform changes in a way that a point may be mapped to a new position"""
        self.__OnChangeEventListeners.add(func)

    def RemoveOnChangeEventListener(self, func: Callable):
        """Unsubscribe to be called when the transform changes in a way that a point may be mapped to a new position"""
        self.__OnChangeEventListeners.remove(func)

    def AddOnPointMovedEventListener(self, func: PointMovedCallback):
        """Subscribe to lightweight notifications during interactive point drag."""
        self.__OnPointMovedEventListeners.add(func)

    def RemoveOnPointMovedEventListener(self, func: PointMovedCallback):
        self.__OnPointMovedEventListeners.remove(func)

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
        if self.interactive_edit_in_progress:
            self._full_refresh_needed = True
            return
        if self.NumPoints > 25:
            self._TransformModel.InitializeDataStructures()  # type: ignore[union-attr]
        self._tile_mesh_cache.clear()
        self.FireOnChangeEvent()

    def _record_point_moved(self, index: int | NDArray[np.integer]) -> None:
        """Track moved control point indices during interactive edit."""
        if isinstance(index, (int, np.integer)):
            self._pending_moved_indices.add(int(index))
        else:
            self._pending_moved_indices.update(int(i) for i in np.atleast_1d(index).tolist())
        self.FireOnPointMovedEvent()

    def FireOnPointMovedEvent(self):
        """Coalesced notification for incremental display updates during drag."""
        if QApplication.instance() is None:
            self._fire_pending_point_moved_event()
            return
        if self._point_moved_event_pending:
            return
        self._point_moved_event_pending = True
        QTimer.singleShot(0, self._fire_pending_point_moved_event)

    def _fire_pending_point_moved_event(self):
        self._point_moved_event_pending = False
        if not self._pending_moved_indices:
            return
        indices = np.array(sorted(self._pending_moved_indices), dtype=np.intp)
        self._pending_moved_indices.clear()
        self.__OnPointMovedEventListeners.invoke(self, indices)

    def FireOnChangeEvent(self):
        """Calls every function registered to be notified when the transform changes.

        Notifications are coalesced: while one is already queued we do not queue another,
        so a burst of changes (e.g. CTRL+scroll rotation firing one event per wheel notch)
        results in a single listener pass against the latest transform state per event-loop
        turn rather than one expensive pass (tile-buffer rebuild + lazy RBF solve) per notch.
        """

        # Calls every listener when the transform has changed in a way that a point may be mapped to a new position in the fixed space
        if QApplication.instance() is None:
            self.__OnChangeEventListeners.invoke(self)
            return

        if self._change_event_pending:
            return

        self._change_event_pending = True
        QTimer.singleShot(0, self._fire_pending_change_event)

    def _fire_pending_change_event(self):
        """Deliver the coalesced OnChange notification queued by FireOnChangeEvent."""
        # Reset first so a change triggered *by* a listener queues a fresh pass instead of
        # being dropped, and so an exception in a listener cannot leave the flag stuck.
        self._change_event_pending = False
        self.__OnChangeEventListeners.invoke(self)

    def FireOnTransformModelChangeEvent(self, old: nornir_imageregistration.ITransform,
                                        new: nornir_imageregistration.ITransform):
        """Calls every function registered to be notified when the transform changes."""

        # Calls every listener when the transform has changed in a way that a point may be mapped to a new position in the fixed space
        #        Pool = pools.GetGlobalThreadPool()
        # tlist = list()
        if QApplication.instance() is None:
            self.__OnTransformModelReplacedEventListeners.invoke(self, old, new)
        else:
            QTimer.singleShot(0, lambda: self.__OnTransformModelReplacedEventListeners.invoke(self, old, new))
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

        self.__OnChangeEventListeners = pyre.qt_eventmanager.QtEventManager[TransformChangedCallback]()
        self.__OnPointMovedEventListeners = pyre.qt_eventmanager.QtEventManager[PointMovedCallback]()
        self.__OnTransformModelReplacedEventListeners = pyre.qt_eventmanager.QtEventManager[TransformModelChangedCallback]()

        self.DefaultToForwardTransform = DefaultToForwardTransform

        self.TransformModel = TransformModel

        if TransformModel is None:
            self.TransformModel = CreateDefaultTransform(nornir_imageregistration.transforms.TransformType.RIGID)

        self.Debug = False
        self.ShowWarped = False
        self._change_event_pending = False
        self._point_moved_event_pending = False
        self._interactive_edit_depth = 0
        self._interactive_edit_space = None
        self._rigid_matrix_at_edit_start = None
        self._rigid_inverse_matrix_at_edit_start = None
        self._pending_moved_indices = set()
        self._tile_mesh_cache = TileMeshCpuCache()
        self._full_refresh_needed = False

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
            self.TransformModel.points = points  # type: ignore[assignment]

        return

    def NextViewMode(self):
        self.ShowWarped = not self.ShowWarped

        if not self.DefaultToForwardTransform:
            self.ShowWarped = False

    def GetFixedPoint(self, index: int):
        return self.TransformModel.TargetPoints[index, :]  # type: ignore[attr-defined]

    def GetWarpedPoint(self, index: int):
        return self.TransformModel.SourcePoints[index, :]  # type: ignore[attr-defined]

    def GetWarpedPointsInRect(self, bounds: nornir_imageregistration.Rectangle):
        return self.TransformModel.GetWarpedPointsInRect(bounds)  # type: ignore[attr-defined]

    def GetFixedPointsInRect(self, bounds: nornir_imageregistration.Rectangle):
        return self.TransformModel.GetFixedPointsInRect(bounds)  # type: ignore[attr-defined]

    def NearestPoint(self, ImagePoint: NDArray[np.floating], space: Space) -> tuple[
        float | NDArray[np.floating] | None, int | NDArray[np.integer] | None]:
        if isinstance(self.TransformModel, IControlPoints):
            if space == Space.Target:
                return self.TransformModel.NearestWarpedPoint(ImagePoint)  # type: ignore[attr-defined]
            else:
                return self.TransformModel.NearestFixedPoint(ImagePoint)  # type: ignore[attr-defined]
        else:
            return None, None

    def TranslateFixed(self, offset: nornir_imageregistration.VectorLike):
        self.TransformModel.TranslateFixed(offset)  # type: ignore[attr-defined]

    def TranslateWarped(self, offset: nornir_imageregistration.VectorLike):
        self.TransformModel.TranslateWarped(offset)  # type: ignore[attr-defined]

    def Translate(self, offset: nornir_imageregistration.VectorLike, space: Space):
        if space == Space.Target:
            self.TransformModel.TranslateWarped(offset)  # type: ignore[attr-defined]
        else:
            self.TransformModel.TranslateFixed(offset)  # type: ignore[attr-defined]

    def Rotate(self, rangle: float, center: NDArray[np.floating] | None = None):
        if isinstance(self._TransformModel, nornir_imageregistration.ITransformTargetRotation):
            self.TransformModel.RotateTargetPoints(-rangle, center)  # type: ignore[attr-defined]
        elif isinstance(self._TransformModel, nornir_imageregistration.ITransformSourceRotation):
            self.TransformModel.RotateSourcePoints(rangle, center)  # type: ignore[attr-defined]
        else:
            raise NotImplementedError("Current transform does not support rotation")

    def FlipWarped(self):
        """
        Flip the target points
        """
        if isinstance(self.TransformModel, nornir_imageregistration.ITransformFlip):
            self.TransformModel.Flip()
        else:
            print("Transform does not support flipping")

    def TryAddPoint(self, ImageX: float, ImageY: float, space: Space = Space.Source):

        if not isinstance(self.TransformModel, nornir_imageregistration.transforms.IControlPointAddRemove):
            print("transform does not support add/remove control points")
            return

        OppositePoint = None
        NewPointPair = []
        if space == Space.Target and not self.ShowWarped:
            OppositePoint = self.TransformModel.Transform([[ImageY, ImageX]])  # type: ignore[arg-type]
            NewPointPair = [OppositePoint[0][0], OppositePoint[0][1], ImageY, ImageX]
        else:
            OppositePoint = self.TransformModel.InverseTransform([[ImageY, ImageX]])  # type: ignore[arg-type]
            NewPointPair = [ImageY, ImageX, OppositePoint[0][0], OppositePoint[0][1]]

        return self.TransformModel.AddPoint(NewPointPair)  # type: ignore[arg-type]

    def TryDeletePoint(self, ImageX: float, ImageY: float, maxDistance: float, space: Space = Space.Source):

        if not isinstance(self.TransformModel, nornir_imageregistration.transforms.IControlPointAddRemove):
            print("transform does not support add/remove control points")
            return

        NearestPoint = None
        index = None
        distance = 0

        try:
            if space == Space.Target and not self.ShowWarped:
                distance, index = self.TransformModel.NearestWarpedPoint([ImageY, ImageX])  # type: ignore[attr-defined, arg-type]
            else:
                distance, index = self.TransformModel.NearestFixedPoint([ImageY, ImageX])  # type: ignore[attr-defined, arg-type]
        except:
            pass;

        if distance > maxDistance:
            return None

        self.TransformModel.RemovePoint(index)  # type: ignore[arg-type]
        return True

    def TryDeletePoints(self, indicies: NDArray[np.integer] | Sequence[int]):

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

    def RemovePoints(self, indicies: NDArray[np.integer]):
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
            Distance, index = self.TransformModel.NearestWarpedPoint([ImageY, ImageX])  # type: ignore[attr-defined, arg-type]
        else:
            Distance, index = self.TransformModel.NearestFixedPoint([ImageY, ImageX])  # type: ignore[attr-defined, arg-type]

        if Distance > maxDistance:
            return None

        index = self.MovePoint(index, ImageDY, ImageDX)  # type: ignore[arg-type]
        return index

    @staticmethod
    def _ensure_numpy_friendly_index(index: int | set[int] | NDArray[np.integer] | list[int] | Sequence[int]) -> NDArray[np.intp] | int:
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

        return index  # type: ignore[return-value]

    def GetPoints(self, index: int | set[int] | NDArray[np.integer] | list[int], space: Space = Space.Source):
        NearestPoint = None
        np_index = self._ensure_numpy_friendly_index(index)

        if isinstance(np_index, np.ndarray):
            if max(np_index) > len(self.TransformModel.SourcePoints):  # type: ignore[attr-defined]
                return None
        else:
            if np_index > len(self.TransformModel.SourcePoints):  # type: ignore[attr-defined]
                return None

        if space == Space.Source:
            return self.TransformModel.SourcePoints[np_index]  # type: ignore[attr-defined]
        else:
            return self.TransformModel.TargetPoints[np_index]  # type: ignore[attr-defined]

    def SetPoint(self, index: int, X: float, Y: float, space: Space = Space.Source) -> int | NDArray[np.integer]:
        """Sets the specified point to the new location.  If the transform does not support editing the specied space,
        the point is changed in the opposite space if possible.  Raises ValueError if the transform does not support
        editing any space"""
        original_point = np.array((Y, X))
        point = original_point

        np_index: int | NDArray[np.integer] = self._ensure_numpy_friendly_index(index)

        if space == Space.Target:
            if isinstance(self.TransformModel, nornir_imageregistration.transforms.ITargetSpaceControlPointEdit):
                np_index = self.TransformModel.UpdateTargetPointsByIndex(np_index, point)  # type: ignore[attr-defined]
            elif isinstance(self.TransformModel, nornir_imageregistration.transforms.ISourceSpaceControlPointEdit):
                new_source_point = self.TransformModel.InverseTransform([point])[0]  # type: ignore[arg-type]
                np_index = self.TransformModel.UpdateSourcePointsByIndex(np_index, new_source_point)  # type: ignore[attr-defined]
            else:
                raise ValueError("Transform does not support editing target points in either source or target space")
        elif space == Space.Source:
            if isinstance(self.TransformModel, nornir_imageregistration.transforms.ISourceSpaceControlPointEdit):
                np_index = self.TransformModel.UpdateSourcePointsByIndex(np_index, point)  # type: ignore[attr-defined]
            elif isinstance(self.TransformModel, nornir_imageregistration.transforms.ITargetSpaceControlPointEdit):
                new_target_point = self.TransformModel.Transform([point])[0]  # type: ignore[arg-type]
                np_index = self.TransformModel.UpdateTargetPointsByIndex(np_index, new_target_point)  # type: ignore[attr-defined]
            else:
                raise ValueError("Transform does not support editing target points in either source or target space")
        else:
            raise ValueError(f"Unexpected value for space: {space}")

        return np_index

    def MovePoint(self, index: int | list[int] | NDArray[np.integer], ImageDX: float, ImageDY: float,
                  space: Space = Space.Source) -> int | NDArray[np.integer]:

        if not isinstance(self.TransformModel, nornir_imageregistration.transforms.IControlPoints):
            return index  # type: ignore[return-value]

        np_index = self._ensure_numpy_friendly_index(index)

        original_point = self.GetPoints(np_index, space)
        if original_point is None:
            print(f"No point found for index {np_index}")
            return index  # type: ignore[return-value]

        point = original_point + numpy.array((ImageDY, ImageDX))

        if space == Space.Source:
            # This code is to manipulate transforms where source space points are fixed.  Instead we move the
            # target points in this case.
            if isinstance(self.TransformModel, nornir_imageregistration.transforms.ISourceSpaceControlPointEdit):
                np_index = self.TransformModel.UpdateSourcePointsByIndex(np_index, point)  # type: ignore[attr-defined]
            else:
                # if not self.ShowWarped:
                #     np_index = self.TransformModel.UpdateSourcePointsByPosition(original_point, point)
                # else:
                if isinstance(index, Iterable):
                    if len(index) > 1:
                        raise NotImplementedError("MovePoint does not support moving multiple points, but it should")

                OldTargetPoint = \
                    self.TransformModel.Transform([[point[0] - ImageDY, point[1] - ImageDX]])[0]  # type: ignore[arg-type]
                NewTargetPoint = self.TransformModel.Transform([point])[0]  # type: ignore[arg-type]

                Delta = OldTargetPoint - NewTargetPoint
                FinalPoint = self.TransformModel.TargetPoints[np_index] + Delta  # type: ignore[attr-defined]
                np_index = self.TransformModel.UpdateTargetPointsByIndex(np_index, FinalPoint)  # type: ignore[attr-defined]

        else:
            if isinstance(self.TransformModel, nornir_imageregistration.transforms.ITargetSpaceControlPointEdit):
                np_index = self.TransformModel.UpdateTargetPointsByIndex(np_index, point)  # type: ignore[attr-defined]
            else:
                # if not self.ShowWarped:
                #     np_index = self.TransformModel.UpdateSourcePointsByPosition(original_point, point)
                # else:
                if isinstance(index, Iterable):
                    if len(index) > 1:
                        raise NotImplementedError("MovePoint does not support moving multiple points, but it should")

                OldSourcePoint = \
                    self.TransformModel.InverseTransform([[point[0] - ImageDY, point[1] - ImageDX]])[0]  # type: ignore[arg-type]
                NewSourcePoint = self.TransformModel.InverseTransform([point])[0]  # type: ignore[arg-type]

                Delta = OldSourcePoint - NewSourcePoint
                FinalPoint = self.TransformModel.SourcePoints[np_index] + Delta  # type: ignore[attr-defined]
                np_index = self.TransformModel.UpdateSourcePointsByIndex(np_index, FinalPoint)  # type: ignore[attr-defined]

                # print(f'Dragged point {str(np_index)} {str(point)}')

        if isinstance(index, Iterable) and not isinstance(np_index, Iterable):
            result = np.array([np_index], dtype=int)
        else:
            result = np_index  # type: ignore[assignment]

        if self.interactive_edit_in_progress:
            self._record_point_moved(result)
        return result
