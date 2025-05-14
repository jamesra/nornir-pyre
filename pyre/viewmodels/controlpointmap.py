import numpy as np
from numpy.typing import NDArray
import scipy.spatial

from pyre.space import Space
from pyre.controllers.transformcontroller import TransformController


class ControlPointMap:
    """
    Has a collection of points that represent a transform,
    creates a searchable spatial data structure,
    and assists in mapping interactions to commands
    """

    _transformcontroller: TransformController
    _kdtree: scipy.spatial.KDTree
    _tween: float | Space
    _cached_tween_points: NDArray[np.floating] = None
    _cached_points: NDArray[np.floating] = None  # The cached source and target points

    def __init__(self, transformcontroller: TransformController,
                 tween: float | Space):
        """

        :param transformcontroller:
        :param tween: Fractional distance between Source and Target Space, 0 = Source, 1 = Target
        """
        self._tween = tween
        self._transformcontroller = transformcontroller
        self._transformcontroller.AddOnChangeEventListener(self._OnTransformChange)
        self.create_kdtree()

    def _OnTransformChange(self, transform_controller: TransformController):
        self.create_kdtree()

    @property
    def points(self) -> NDArray[np.floating]:
        return self._cached_points

    @property
    def tween(self) -> float | Space:
        if self._tween == 0:
            return Space.Source
        elif self._tween == 1:
            return Space.Target

        return self._tween

    @tween.setter
    def tween(self, value: float | Space):
        self._tween = value
        self.create_kdtree()

    @property
    def cached_tween_points(self) -> NDArray[np.floating]:
        return self._kdtree.data

    @staticmethod
    def tweened_points(transform_controller: TransformController, tween: float | Space) -> NDArray[np.floating]:
        """The control points in the transform, mapped as necessary"""
        if tween == Space.Source:
            return transform_controller.SourcePoints
        elif tween == Space.Target:
            return transform_controller.TargetPoints
        else:
            return (transform_controller.SourcePoints * (1.0 - tween) +
                    transform_controller.TargetPoints * tween)

    def create_kdtree(self):
        """Create a KDTree from the current control points, if they have changed"""
        new_points = self.tweened_points(self._transformcontroller, self.tween)
        if self._cached_points is not None and \
                np.allclose(self._cached_points.shape, new_points.shape) and \
                np.allclose(self._cached_points, new_points):
            """If there is no change, do not rebuild expensive KDTree"""
            return

        self._kdtree = scipy.spatial.KDTree(new_points,
                                            copy_data=True,
                                            # Copy data.  If the transform changes we need to notice so we can regenerate
                                            balanced_tree=True)
        self._cached_points = new_points

        # print('KDTree created')

    def find_nearest_within(self, points: NDArray[np.floating], max_distance: float) -> set[int]:
        """Find the nearest point to the given point within max_distance"""
        return set(self._kdtree.query_ball_point(points,
                                                 r=max_distance,
                                                 return_sorted=True))
