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
                # Interpolators pass through control points: Transform(SourcePoints) == TargetPoints.
                target_pts = _as_numpy_f64(transform_controller.TargetPoints)
                return target_pts
            if tween == Space.Target:
                return _as_numpy_f64(transform_controller.TargetPoints)
        if tween == Space.Source:
            return _as_numpy_f64(transform_controller.SourcePoints)
        elif tween == Space.Target:
            return _as_numpy_f64(transform_controller.TargetPoints)
        return _as_numpy_f64(
            transform_controller.SourcePoints * (1.0 - tween) +
            transform_controller.TargetPoints * tween)

    def create_kdtree(self):
        """Create a KDTree from the current control points, if they have changed.

        Cache a snapshot, not a view of the live TargetPoints/SourcePoints arrays.
        In-place edits would otherwise compare the cache to itself and skip rebuilds,
        leaving Target-view picking on stale coordinates.
        """
        new_points = _as_numpy_f64(
            self.tweened_points(self._transformcontroller, self.tween, self._view_type))
        if (self._cached_points is not None and
                self._cached_points.shape == new_points.shape and
                np.allclose(self._cached_points, new_points)):
            return

        self._kdtree = scipy.spatial.KDTree(new_points,
                                            copy_data=True,
                                            balanced_tree=True)
        self._cached_points = np.array(new_points, dtype=np.float64, copy=True)

        # print('KDTree created')

    def find_nearest_within(self, points: NDArray[np.floating], max_distance: float) -> set[int]:
        """Find the single nearest point within max_distance (avoids multi-select when zoomed out)."""
        query = np.asarray(points, dtype=np.float64).reshape(-1, 2)
        if query.size == 0 or not np.all(np.isfinite(query)):
            # InverseTransform/Transform can yield NaN outside the mesh (e.g. right after
            # delete while RBF prewarm forces extrapolate=False). Treat as no hit.
            return set()
        if query.shape[0] != 1:
            results = self._kdtree.query_ball_point(query, r=max_distance, return_sorted=True)
            return {int(i) for sub in results for i in sub}

        distance, index = self._kdtree.query(query[0])
        if distance <= max_distance:
            return {int(index)}
        return set()

    def find_in_rect(
            self,
            corner_a: NDArray[np.floating] | object,
            corner_b: NDArray[np.floating] | object,
    ) -> set[int]:
        """Return indices of control points inside an axis-aligned rectangle (inclusive)."""
        a = np.asarray(corner_a, dtype=np.float64).reshape(-1)
        b = np.asarray(corner_b, dtype=np.float64).reshape(-1)
        if a.size < 2 or b.size < 2 or not np.all(np.isfinite(a[:2])) or not np.all(np.isfinite(b[:2])):
            return set()
        pts = np.asarray(self.points, dtype=np.float64)
        if pts.size == 0:
            return set()
        y0, x0 = np.minimum(a[:2], b[:2])
        y1, x1 = np.maximum(a[:2], b[:2])
        finite = np.isfinite(pts).all(axis=1)
        inside = finite & (pts[:, 0] >= y0) & (pts[:, 0] <= y1) & (pts[:, 1] >= x0) & (pts[:, 1] <= x1)
        return {int(i) for i in np.nonzero(inside)[0]}

    def find_in_polygon(self, vertices: NDArray[np.floating] | object) -> set[int]:
        """Return indices of control points inside a polygon, including the boundary."""
        verts = np.asarray(vertices, dtype=np.float64).reshape(-1, 2)
        finite_v = verts[np.isfinite(verts).all(axis=1)]
        if finite_v.shape[0] < 3:
            return set()
        pts = np.asarray(self.points, dtype=np.float64)
        if pts.size == 0:
            return set()
        finite = np.isfinite(pts).all(axis=1)
        inside = np.zeros(pts.shape[0], dtype=bool)
        inside[finite] = _even_odd_contains(pts[finite], finite_v) | _points_on_polygon_boundary(
            pts[finite], finite_v)
        return {int(i) for i in np.nonzero(inside)[0]}


def _even_odd_contains(points: NDArray[np.floating], vertices: NDArray[np.floating]) -> NDArray[np.bool_]:
    """Even-odd fill test. ``points`` and ``vertices`` are (y, x)."""
    if not np.allclose(vertices[0], vertices[-1]):
        ring = np.vstack([vertices, vertices[0:1]])
    else:
        ring = vertices
    y = points[:, 0][:, None]
    x = points[:, 1][:, None]
    y0 = ring[:-1, 0]
    x0 = ring[:-1, 1]
    y1 = ring[1:, 0]
    x1 = ring[1:, 1]
    crosses = ((y0 <= y) & (y1 > y)) | ((y1 <= y) & (y0 > y))
    dy = y1 - y0
    x_int = x0 + (y - y0) * (x1 - x0) / np.where(dy == 0.0, 1.0, dy)
    return (np.sum(crosses & (x < x_int), axis=1) % 2) == 1


def _points_on_polygon_boundary(
        points: NDArray[np.floating],
        vertices: NDArray[np.floating],
        epsilon: float = 1e-9,
) -> NDArray[np.bool_]:
    """True when a point lies on any polygon edge."""
    if not np.allclose(vertices[0], vertices[-1]):
        ring = np.vstack([vertices, vertices[0:1]])
    else:
        ring = vertices
    p = points[:, None, :]
    a = ring[:-1][None, :, :]
    b = ring[1:][None, :, :]
    ab = b - a
    ap = p - a
    ab_len2 = np.sum(ab * ab, axis=2)
    ab_len2 = np.where(ab_len2 == 0.0, 1.0, ab_len2)
    t = np.clip(np.sum(ap * ab, axis=2) / ab_len2, 0.0, 1.0)
    closest = a + t[:, :, None] * ab
    dist2 = np.sum((p - closest) ** 2, axis=2)
    return np.any(dist2 <= epsilon * epsilon, axis=1)
