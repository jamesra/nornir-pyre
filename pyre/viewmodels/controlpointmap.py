import numpy as np
from numpy.typing import NDArray
import scipy.spatial

from pyre.space import Space
from pyre.interfaces.viewtype import ViewType
from pyre.controllers.transformcontroller import TransformController
import nornir_imageregistration


def _as_numpy_f64(values: NDArray[np.floating] | object) -> NDArray[np.floating]:
    """Convert transform output to host float64 for hit-testing paths."""
    if hasattr(values, "get"):
        values = values.get()  # type: ignore[union-attr]
    return np.asarray(values, dtype=np.float64)


class ControlPointMap:
    """
    Has a collection of points that represent a transform,
    creates a searchable spatial data structure,
    and assists in mapping interactions to commands
    """

    _transformcontroller: TransformController
    _kdtree: scipy.spatial.KDTree
    _tween: float | Space
    _view_type: ViewType | None
    _cached_tween_points: NDArray[np.floating] | None = None
    _cached_points: NDArray[np.floating] | None = None  # The cached source and target points

    def __init__(self, transformcontroller: TransformController,
                 tween: float | Space,
                 view_type: ViewType | None = None):
        """

        :param transformcontroller:
        :param tween: Fractional distance between Source and Target Space, 0 = Source, 1 = Target
        :param view_type: When Composite, mesh/grid hit-test uses target display space.
        """
        self._tween = tween
        self._view_type = view_type
        self._transformcontroller = transformcontroller
        self._transformcontroller.AddOnChangeEventListener(self._OnTransformChange)
        self._transformcontroller.AddOnPointMovedEventListener(self._OnPointMoved)
        self.create_kdtree()

    def _OnTransformChange(self, transform_controller: TransformController):
        self.create_kdtree()

    def _OnPointMoved(self, transform_controller: TransformController, indices: NDArray[np.integer]):
        self.create_kdtree()

    @property
    def points(self) -> NDArray[np.floating]:
        assert self._cached_points is not None
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
    def shader_tween_for_panel_space(space: Space) -> float:
        """Shader tween for panel space (0 = SourcePoints, 1 = TargetPoints).

        Shader mix(point_source_offset, point_target_offset, tween) with the GL
        pointset layout yields tween=0 for SourcePoints and tween=1 for TargetPoints.
        """
        return 0.0 if space == Space.Source else 1.0

    @staticmethod
    def draw_tween_for_pyre_space(space: Space) -> float:
        """Deprecated alias for :meth:`shader_tween_for_panel_space`."""
        return ControlPointMap.shader_tween_for_panel_space(space)

    @staticmethod
    def tweened_points(
            transform_controller: TransformController,
            tween: float | Space,
            view_type: ViewType | None = None,
    ) -> NDArray[np.floating]:
        """Control points for hit-testing in Pyre panel space (Source=SourcePoints, Target=TargetPoints)."""
        model = transform_controller.TransformModel
        if (
                view_type == ViewType.Composite
                and model is not None
                and not isinstance(model, nornir_imageregistration.IRigidTransform)
        ):
            if tween == Space.Source:
                source_pts = transform_controller.SourcePoints
                return _as_numpy_f64(transform_controller.Transform(source_pts))
            if tween == Space.Target:
                return transform_controller.TargetPoints
        if tween == Space.Source:
            return transform_controller.SourcePoints
        elif tween == Space.Target:
            return transform_controller.TargetPoints
        return (transform_controller.SourcePoints * (1.0 - tween) +
                transform_controller.TargetPoints * tween)

    def create_kdtree(self):
        """Create a KDTree from the current control points, if they have changed"""
        new_points = self.tweened_points(self._transformcontroller, self.tween, self._view_type)
        if self._cached_points is not None and \
                self._cached_points.shape == new_points.shape and \
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
        """Find the single nearest point within max_distance (avoids multi-select when zoomed out)."""
        query = np.asarray(points, dtype=np.float64).reshape(-1, 2)
        if query.shape[0] != 1:
            results = self._kdtree.query_ball_point(query, r=max_distance, return_sorted=True)
            return {int(i) for sub in results for i in sub}

        distance, index = self._kdtree.query(query[0])
        if distance <= max_distance:
            return {int(index)}
        return set()
