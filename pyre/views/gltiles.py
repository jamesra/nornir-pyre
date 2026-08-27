"""
Contains routines that divide a transform and image into tiles that fit into a GPU's texture size.
"""
import dataclasses
from typing import Any, Callable

import numpy as np
from numpy.typing import NDArray
import scipy.spatial
import scipy.spatial.distance

import nornir_imageregistration
from nornir_imageregistration import cp
from nornir_imageregistration.transforms.base import (
    IControlPoints,
    IGridTransform,
    IRigidTransform,
    ITriangulatedSourceSpace,
)
from nornir_imageregistration.transforms.triangulation import (
    apply_barycentric_stencil,
    barycentric_sample_delaunay,
    barycentric_stencil_delaunay,
    barycentric_weights_in_triangle,
)
from pyre.gl_engine import DynamicVAO, GLBuffer, GLIndexBuffer, ShaderVAO
from pyre.space import Space
from pyre.perf_debug import timed


@dataclasses.dataclass
class RenderCache:
    """This object stores variables that must be calculated every time the transform changes"""

    FixedImageDataGrid: None | list[list[ShaderVAO | None]] = None
    WarpedImageDataGrid: None | list[list[ShaderVAO | None]] = None
    LastSelectedPointIndex: int | None = None
    PointCache: Any = None

    def __del__(self):
        self.PointCache = None
        self.FixedImageDataGrid = None
        self.WarpedImageDataGrid = None
        self.LastSelectedPointIndex = None


@dataclasses.dataclass
class TileGLObjects:
    """Stores the GL Buffers and VAO for a tile.
    Buffers can be updated with new values to adapt to transform changes."""
    vertex_buffer: GLBuffer
    index_buffer: GLIndexBuffer
    vao: DynamicVAO
    cached_simplices: NDArray[np.integer] | None = None
    point_count: int = 0
    is_rigid_quad: bool = False
    mesh_populated: bool = False
    cp_indices: NDArray[np.integer] | None = None
    cp_weights: NDArray[np.floating] | None = None


RenderDataMap = dict[
    tuple[int, int], TileGLObjects]  # Map from grid coordinates to render data for the tile at that grid


def _tile_grid_points(tile_bounding_rect: nornir_imageregistration.Rectangle,
                      grid_size: tuple[int, int] = (8, 8)):
    """
    :return: Fills the tile area with a (MxN) grid of points.  Maps the points through the transform.  Then adds the known transform points to the results
    """

    (y, x) = tile_bounding_rect.BottomLeft
    h = int(tile_bounding_rect.Height)
    w = int(tile_bounding_rect.Width)

    # target_corners_o = [[y, x],
    #                   [y, x + w, ],
    #                   [y + h, x],
    #                   [y + h, x + w]]

    grid_size = (int(grid_size[0]), int(grid_size[1]))
    warped_corners = np.zeros(((grid_size[0] + 1) * (grid_size[1] + 1), 2), dtype=np.float32)

    xstep = int(w / grid_size[1])
    ystep = int(h / grid_size[0])

    for iX in range(0, grid_size[1] + 1):
        for iY in range(0, grid_size[0] + 1):
            warped_corners[(iX * (grid_size[0] + 1)) + iY] = (y + (iY * ystep), x + (iX * xstep))

    # for xtemp in range(0, w + 1, xstep):
    # for ytemp in range(0, h + 1, ystep):
    # target_corners.append([ytemp + y, xtemp + x])

    # target_corners = np.array(target_corners, dtype=np.float32)

    return warped_corners


def _tile_bounding_points(tile_bounding_rect: nornir_imageregistration.Rectangle,
                          grid_size: tuple[int, int] = (3, 3)) -> NDArray[np.floating]:
    """
    :return: Returns a set of point pairs mapping the boundaries of the image tile
    """

    (y, x) = tile_bounding_rect.BottomLeft
    h = int(tile_bounding_rect.Height)
    w = int(tile_bounding_rect.Width)

    warped_corners = [[y, x],
                      [y, x + w, ],
                      [y + h, x],
                      [y + h, x + w]]

    xstep = w // grid_size[1]
    ystep = h // grid_size[0]

    for ytemp in range(0, h + 1, int(ystep)):
        warped_corners.append([ytemp + y, 0 + x])
        warped_corners.append([ytemp + y, w + x])

    for xtemp in range(1, w, int(xstep)):
        warped_corners.append([0 + y, xtemp + x])
        warped_corners.append([h + y, xtemp + x])

    warped_corners = np.array(warped_corners, dtype=np.float32)

    return warped_corners


def _point_pairs_to_numpy_f64(point_pairs: NDArray[np.floating]) -> NDArray[np.floating]:
    """Host float64 point pairs for scipy.Delaunay / OpenGL mesh build (CuPy -> NumPy)."""
    return nornir_imageregistration.EnsureNumpyArray(point_pairs, dtype=np.float64)


def _find_corresponding_points(transform: nornir_imageregistration.ITransform,
                               points: NDArray[np.floating],
                               forward_transform: bool,
                               *,
                               extrapolate: bool = True) -> NDArray[np.floating]:
    """Map points through the transform as Nx4 (warped, fixed) pairs.

    Pairs stay on the Transform output backend until a Delaunay/GL host conversion.
    """
    pts_for_transform = nornir_imageregistration.EnsurePointsAre2DArray(points)
    if forward_transform:
        mapped = transform.Transform(pts_for_transform, extrapolate=extrapolate)
        warped_points = mapped
        fixed_points = points
    else:
        mapped = transform.InverseTransform(pts_for_transform, extrapolate=extrapolate)
        warped_points = points
        fixed_points = mapped

    xp = cp.get_array_module(mapped)
    return xp.hstack((
        xp.asarray(warped_points, dtype=xp.float32),
        xp.asarray(fixed_points, dtype=xp.float32),
    ))


def _tile_bounding_rect(transform: nornir_imageregistration.ITransform,
                        tile_bounding_rect: nornir_imageregistration.Rectangle,
                        forward_transform: bool = True,
                        grid_size: tuple[int, int] = (3, 3)) -> nornir_imageregistration.Rectangle:
    """
    :return: Returns a bounding rectangle built from points placed around the edge of the tile
    """
    border_points = _tile_bounding_points(tile_bounding_rect=tile_bounding_rect,
                                          grid_size=grid_size)
    border_point_pairs = _find_corresponding_points(transform, border_points,
                                                    forward_transform=forward_transform)
    return nornir_imageregistration.spatial.Rectangle.CreateFromBounds(
        nornir_imageregistration.spatial.BoundsArrayFromPoints(border_point_pairs[:, 0:2]))


def _merge_point_pairs_with_transform(points_a: NDArray[np.floating],
                                      transform_points: NDArray[np.floating]) -> NDArray[np.floating]:
    """
    Extracts control points from a transform, merges them with the input points, and returns the result.
    Removes duplicates.
    :param points_a:
    :param transform_points:
    :return:
    """

    # Transforms use source/target terminology in Pyre; nornir APIs may still say warped/fixed.
    # The transform maps target-space points into source space.
    points_b = transform_points
    if len(points_a) > 0 and len(points_b) > 0:
        xp = cp.get_array_module(points_a, points_b)
        all_point_pairs = xp.vstack([xp.asarray(points_a), xp.asarray(points_b)])
        unique_point_pairs = nornir_imageregistration.core.remove_duplicate_points(
            all_point_pairs, [1, 0])
        return unique_point_pairs

    if len(points_a) > 0:
        return points_a

    if len(points_b) > 0:
        return points_b
    return np.array([])


def _build_subtile_point_pairs(transform: nornir_imageregistration.ITransform,
                               rect: nornir_imageregistration.Rectangle,
                               forward_transform: bool = True, ) -> NDArray[np.floating]:
    """Determine transform points for a subregion of the transform"""
    tile_points = _tile_grid_points(rect)
    tile_point_pairs = _find_corresponding_points(transform, tile_points,
                                                  forward_transform=forward_transform)
    transform_point_pairs = np.concatenate(
        np.array(transform.GetWarpedPointsInRect(rect.ToArray())),  # type: ignore[attr-defined]
        2).squeeze()
    return _merge_point_pairs_with_transform(tile_point_pairs, transform_point_pairs)


def _build_tile_point_pairs(transform: nornir_imageregistration.ITransform,
                            rect: nornir_imageregistration.Rectangle,
                            forward_transform: bool = True, ) -> NDArray[np.floating]:
    """
    Determine transform points the live within the bounding rectangle, adding points around the boundary of the bounding rectangle to the result set.
    """

    border_points = _tile_bounding_points(rect)
    border_point_pairs = _find_corresponding_points(transform, border_points,
                                                    forward_transform=forward_transform)
    if isinstance(transform, nornir_imageregistration.IControlPoints):
        return _merge_point_pairs_with_transform(border_point_pairs, transform.points)
    else:
        return border_point_pairs


def _z_values_for_points_by_texture(texture_points: NDArray[np.floating]) -> NDArray[np.floating]:
    """
    :param texture_points:
    :return: A Z depth for each vertex, which is equal to the distance of the vertex from the center (average) of the points
    """
    centered_points = texture_points - 0.5
    z = np.power(centered_points, 2).sum(axis=1)
    z = np.sqrt(z)
    return z


def _texture_coordinates(points_yx: NDArray[np.floating],
                         bounding_rect: nornir_imageregistration.Rectangle) -> NDArray[np.floating]:
    """
    Given a set of points inside a bounding rectangle that represents the texture space,
     return the texture coordinates for each point.
    Uses a half-texel offset so we sample texel centers instead of edges; avoids corner
    artifacts (noise at tile boundaries) when filtering with LINEAR.
    :param points_yx: Points to generate texture coordinates for
    :param bounding_rect: Bounding rectangle for the texture space
    :return: texture coordinates for a rectangle in fixed (source) space
    """
    # Ensure numpy: transform may return CuPy arrays; mixing with np.array() causes TypeError
    points_yx = np.asarray(points_yx, dtype=np.float64)
    size = np.array(bounding_rect.Size, dtype=np.float64)
    # +0.5 so the first texel center is at (0.5/w, 0.5/h) instead of sampling at (0,0) edge
    texture_points = (points_yx - np.array(bounding_rect.BottomLeft) + 0.5) / size
    half_texel = 0.5 / size
    np.clip(texture_points[:, 0], half_texel[0], 1.0 - half_texel[0], out=texture_points[:, 0])
    np.clip(texture_points[:, 1], half_texel[1], 1.0 - half_texel[1], out=texture_points[:, 1])
    # Need to convert texture coordinates to X,Y coordinates (u, v) for the shader
    texture_points = np.fliplr(texture_points)
    return texture_points


def _render_data_for_transform_point_pairs(point_pairs: NDArray[np.floating],
                                           tile_bounding_rect: nornir_imageregistration.Rectangle,
                                           space: Space,
                                           z: float | None = None,
                                           ) -> tuple[NDArray[np.floating], NDArray[np.uint16]]:
    """
    Generate vertices (source, target and texture coordinates) for a set of transform points and the
    indices to render them as triangles
    :return: Verts3D, indices, Verts3d is Source (X,Y,Z), Target (X,Y,Z), Texture (U,V)
    """
    # Ensure numpy: transform may return CuPy arrays; scipy.Delaunay and np.vstack require numpy. OpenGL buffers need host memory.
    point_pairs = _point_pairs_to_numpy_f64(point_pairs)

    fixed_points_yx, warped_points_yx = np.hsplit(point_pairs, 2)

    # tile_bounding_rect = nornir_imageregistration.spatial.BoundingPrimitiveFromPoints(SourcePoints)
    # Need to convert from Y,x to X,Y coordinates
    # fixed_points_xy = np.fliplr(fixed_points_yx)
    # warped_points_xy = np.fliplr(warped_points_yx)
    # Do triangulation before we transform the points to prevent concave edges having a texture mapped over them.

    # texturePoints = (fixed_points_xy - np.array((x,y))) / np.array((w,h))

    texture_points = _texture_coordinates(
        warped_points_yx if space == Space.Source else fixed_points_yx,
        bounding_rect=tile_bounding_rect)
    # print(str(texturePoints[0, :]))
    tri = scipy.spatial.Delaunay(texture_points)
    # np.array([[(u - x) / float(w), (v - y) / float(h)] for u, v in fixed_points_xy], dtype=np.float32)

    # Set vertex z according to distance from center
    if z is not None:
        z_array = np.ones((fixed_points_yx.shape[0], 1)) * z
    else:
        z_array = _z_values_for_points_by_texture(texture_points)

    verts3d = np.vstack((fixed_points_yx[:, 1],
                         fixed_points_yx[:, 0],
                         z_array.flat,
                         warped_points_yx[:, 1],
                         warped_points_yx[:, 0],
                         z_array.flat,
                         texture_points[:, 0],
                         texture_points[:, 1])).T

    verts3d = verts3d.astype(np.float32)

    indicies = tri.simplices.flatten().astype(np.uint16)

    return verts3d, indicies


def is_rigid_transform(transform: nornir_imageregistration.ITransform) -> bool:
    return isinstance(transform, IRigidTransform)


def _rigid_tile_quad_render_data(tile_bounding_rect: nornir_imageregistration.Rectangle,
                                 space: Space,
                                 z: float | None = None) -> tuple[NDArray[np.floating], NDArray[np.uint16]]:
    """Static two-triangle quad for a tile; warping is applied in the vertex shader for rigid transforms."""
    (y, x) = tile_bounding_rect.BottomLeft
    h = float(tile_bounding_rect.Height)
    w = float(tile_bounding_rect.Width)
    corners_yx = np.array([[y, x], [y, x + w], [y + h, x + w], [y + h, x]], dtype=np.float64)
    texture_points = _texture_coordinates(corners_yx, tile_bounding_rect)
    if z is not None:
        z_array = np.ones((4, 1), dtype=np.float64) * z
    else:
        z_array = _z_values_for_points_by_texture(texture_points).reshape(-1, 1)
    verts3d = np.hstack((
        corners_yx[:, 1:2], corners_yx[:, 0:1], z_array,
        corners_yx[:, 1:2], corners_yx[:, 0:1], z_array,
        texture_points,
    )).astype(np.float32)
    indices = np.array([0, 1, 2, 0, 2, 3], dtype=np.uint16)
    return verts3d, indices


def _triangle_orientations(texture_points: NDArray[np.floating],
                           simplices: NDArray[np.integer]) -> NDArray[np.floating]:
    areas = []
    for tri in simplices:
        p = texture_points[tri]
        areas.append((p[1, 0] - p[0, 0]) * (p[2, 1] - p[0, 1]) - (p[2, 0] - p[0, 0]) * (p[1, 1] - p[0, 1]))
    return np.asarray(areas, dtype=np.float64)


def _simplices_compatible_with_points(
        simplices: NDArray[np.integer] | None,
        point_count: int,
        cached_point_count: int) -> bool:
    """True when cached Delaunay indices match the current per-tile point set."""
    if simplices is None or simplices.size == 0 or point_count <= 0:
        return False
    if point_count != cached_point_count:
        return False
    max_idx = int(np.max(simplices))
    min_idx = int(np.min(simplices))
    return min_idx >= 0 and max_idx < point_count


def _simplices_index_in_bounds(
        simplices: NDArray[np.integer] | None,
        point_count: int) -> bool:
    """True when every simplex vertex index refers to a row in texture_points."""
    if simplices is None or simplices.size == 0 or point_count <= 0:
        return False
    return int(np.min(simplices)) >= 0 and int(np.max(simplices)) < point_count


def _topology_still_valid(texture_points: NDArray[np.floating],
                          simplices: NDArray[np.integer]) -> bool:
    if simplices is None or simplices.size == 0:
        return False
    if not _simplices_index_in_bounds(simplices, texture_points.shape[0]):
        return False
    areas = _triangle_orientations(texture_points, simplices)
    if areas.size == 0:
        return False
    signs = np.sign(areas)
    if np.any(areas == 0):
        return False
    return bool(np.all(signs == signs[0]))


def _edge_key(i: int, j: int) -> tuple[int, int]:
    return (i, j) if i < j else (j, i)


def _point_in_circumcircle(p: NDArray[np.floating],
                           a: NDArray[np.floating],
                           b: NDArray[np.floating],
                           c: NDArray[np.floating]) -> bool:
    """Return True if p lies inside the circumcircle of triangle abc."""
    ax, ay = float(a[0] - p[0]), float(a[1] - p[1])
    bx, by = float(b[0] - p[0]), float(b[1] - p[1])
    cx, cy = float(c[0] - p[0]), float(c[1] - p[1])
    det = (ax * ax + ay * ay) * (bx * cy - cx * by)
    det -= (bx * bx + by * by) * (ax * cy - cx * ay)
    det += (cx * cx + cy * cy) * (ax * by - bx * ay)
    orient = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    if orient < 0:
        det = -det
    return det > 0


def _repair_delaunay_by_edge_flips(texture_points: NDArray[np.floating],
                                   simplices: NDArray[np.integer],
                                   max_flips: int = 128) -> NDArray[np.integer] | None:
    """Lawson edge-flip repair on a fixed point set; returns None if repair fails."""
    if not _simplices_index_in_bounds(simplices, texture_points.shape[0]):
        return None
    simp = np.asarray(simplices, dtype=np.intp).copy()
    flips = 0
    changed = True
    while changed and flips < max_flips:
        changed = False
        edge_to_tris: dict[tuple[int, int], list[int]] = {}
        for ti, tri in enumerate(simp):
            for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
                edge_to_tris.setdefault(_edge_key(int(a), int(b)), []).append(ti)

        for (i, j), tri_indices in edge_to_tris.items():
            if len(tri_indices) != 2:
                continue
            t0, t1 = tri_indices
            verts0 = set(int(v) for v in simp[t0])
            verts1 = set(int(v) for v in simp[t1])
            opp = list((verts0 ^ verts1) - {i, j})
            if len(opp) != 2:
                continue
            k, l = opp
            pi, pj, pk, pl = texture_points[i], texture_points[j], texture_points[k], texture_points[l]
            if not (_point_in_circumcircle(pl, pi, pj, pk) or _point_in_circumcircle(pk, pi, pj, pl)):
                continue
            simp[t0] = np.array([k, l, i], dtype=np.intp)
            simp[t1] = np.array([k, l, j], dtype=np.intp)
            flips += 1
            changed = True
            break

    if not _topology_still_valid(texture_points, simp):
        return None
    return simp


def _render_data_with_cached_simplices(point_pairs: NDArray[np.floating],
                                       tile_bounding_rect: nornir_imageregistration.Rectangle,
                                       space: Space,
                                       simplices: NDArray[np.integer],
                                       z: float | None = None,
                                       require_valid_topology: bool = True) -> NDArray[np.floating]:
    point_pairs = _point_pairs_to_numpy_f64(point_pairs)
    fixed_points_yx, warped_points_yx = np.hsplit(point_pairs, 2)
    texture_points = _texture_coordinates(
        warped_points_yx if space == Space.Source else fixed_points_yx,
        bounding_rect=tile_bounding_rect)
    if require_valid_topology and not _topology_still_valid(texture_points, simplices):
        raise ValueError('topology invalid')
    if z is not None:
        z_array = np.ones((fixed_points_yx.shape[0], 1)) * z
    else:
        z_array = _z_values_for_points_by_texture(texture_points)
    verts3d = np.vstack((fixed_points_yx[:, 1],
                         fixed_points_yx[:, 0],
                         z_array.flat,
                         warped_points_yx[:, 1],
                         warped_points_yx[:, 0],
                         z_array.flat,
                         texture_points[:, 0],
                         texture_points[:, 1])).T.astype(np.float32)
    return verts3d


def _regular_grid_cell_simplices(ny: int, nx: int) -> NDArray[np.intp]:
    """Two triangles per cell of a row-major (ny, nx) lattice."""
    if ny < 2 or nx < 2:
        return np.empty((0, 3), dtype=np.intp)
    i, j = np.mgrid[0:ny - 1, 0:nx - 1]
    a = i * nx + j
    b = a + 1
    c = a + nx
    d = c + 1
    return np.concatenate(
        (
            np.stack((a, c, b), axis=-1).reshape(-1, 3),
            np.stack((b, c, d), axis=-1).reshape(-1, 3),
        ),
        axis=0).astype(np.intp)


def _closed_interval_axis_samples(
        axis: NDArray[np.floating],
        lo: float,
        hi: float) -> NDArray[np.float64]:
    """Inclusive tile-edge samples plus lattice coordinates on [lo, hi].

    Interior lattice samples are control-point source coordinates, so warped
    vertices coincide with those CPs. The endpoints keep neighboring texture
    crops on the same bilinear-sampled seam (e.g. source x=4096).
    """
    lo_f = float(lo)
    hi_f = float(hi)
    if hi_f < lo_f:
        lo_f, hi_f = hi_f, lo_f
    axis_f = np.asarray(axis, dtype=np.float64)
    on_interval = axis_f[(axis_f >= lo_f) & (axis_f <= hi_f)]
    samples = np.unique(np.concatenate((np.array((lo_f, hi_f), dtype=np.float64), on_interval)))
    if samples.shape[0] < 2:
        return np.array((lo_f, hi_f), dtype=np.float64)
    return samples


def _grid_tile_mesh_point_pairs(
        transform: IGridTransform,
        tile_rect: nornir_imageregistration.Rectangle,
) -> tuple[NDArray[np.floating], NDArray[np.intp]] | None:
    """Control-point pairs and regular-grid triangles covering one texture tile.

    Vertices are the tensor product of tile-edge samples and in-tile lattice
    coordinates. That keeps neighboring crops on a shared warped seam while
    placing every in-tile control point on a mesh vertex.
    """
    dims = getattr(transform, 'grid_dims', None)
    if dims is None:
        dims = transform.grid.grid_dims
    ny, nx = int(dims[0]), int(dims[1])
    source = nornir_imageregistration.EnsureNumpyArray(transform.SourcePoints)
    target = nornir_imageregistration.EnsureNumpyArray(transform.TargetPoints)
    if source.shape[0] != ny * nx or target.shape[0] != ny * nx:
        return None
    source_g = source.reshape(ny, nx, 2)
    target_g = target.reshape(ny, nx, 2)
    y0, x0 = tile_rect.BottomLeft
    y1 = float(y0) + float(tile_rect.Height)
    x1 = float(x0) + float(tile_rect.Width)
    axis_y = np.asarray(source_g[:, 0, 0], dtype=np.float64)
    axis_x = np.asarray(source_g[0, :, 1], dtype=np.float64)
    ys = _closed_interval_axis_samples(axis_y, float(y0), y1)
    xs = _closed_interval_axis_samples(axis_x, float(x0), x1)
    sub_ny = int(ys.shape[0])
    sub_nx = int(xs.shape[0])
    yy, xx = np.meshgrid(ys, xs, indexing='ij')
    src = np.column_stack((yy.ravel(), xx.ravel()))
    tgt = _bilinear_sample_grid(src, axis_y, axis_x, target_g)
    if tgt.shape[0] != src.shape[0] or not np.all(np.isfinite(tgt)):
        return None
    pairs = np.hstack((tgt, src))
    simplices = _regular_grid_cell_simplices(sub_ny, sub_nx)
    if simplices.shape[0] == 0:
        return None
    return pairs, simplices


def _bilinear_sample_grid(
        query_yx: NDArray[np.floating],
        axis_y: NDArray[np.floating],
        axis_x: NDArray[np.floating],
        values: NDArray[np.floating]) -> NDArray[np.floating]:
    """Bilinear sample of a regular (Y, X) value grid, clamping to the lattice bounds."""
    y = np.asarray(query_yx[:, 0], dtype=np.float64)
    x = np.asarray(query_yx[:, 1], dtype=np.float64)
    axis_y = np.asarray(axis_y, dtype=np.float64)
    axis_x = np.asarray(axis_x, dtype=np.float64)
    ny = int(axis_y.shape[0])
    nx = int(axis_x.shape[0])
    if ny < 1 or nx < 1:
        return np.full((query_yx.shape[0], values.shape[-1]), np.nan, dtype=np.float64)
    if ny == 1 and nx == 1:
        return np.broadcast_to(values[0, 0], (query_yx.shape[0], values.shape[-1])).copy()
    iy1 = np.clip(np.searchsorted(axis_y, y, side='right'), 1, max(ny - 1, 1))
    ix1 = np.clip(np.searchsorted(axis_x, x, side='right'), 1, max(nx - 1, 1))
    iy0 = np.clip(iy1 - 1, 0, ny - 1)
    ix0 = np.clip(ix1 - 1, 0, nx - 1)
    y0 = axis_y[iy0]
    y1 = axis_y[iy1]
    x0 = axis_x[ix0]
    x1 = axis_x[ix1]
    dy = y1 - y0
    dx = x1 - x0
    ty = np.where(dy > 0.0, (y - y0) / dy, 0.0)
    tx = np.where(dx > 0.0, (x - x0) / dx, 0.0)
    np.clip(ty, 0.0, 1.0, out=ty)
    np.clip(tx, 0.0, 1.0, out=tx)
    v00 = values[iy0, ix0]
    v01 = values[iy0, ix1]
    v10 = values[iy1, ix0]
    v11 = values[iy1, ix1]
    ty = ty[:, np.newaxis]
    tx = tx[:, np.newaxis]
    return (v00 * (1.0 - ty) * (1.0 - tx)
            + v01 * (1.0 - ty) * tx
            + v10 * ty * (1.0 - tx)
            + v11 * ty * tx)


def _source_space_delaunay(
        transform: IControlPoints,
        source_points: NDArray[np.floating],
) -> scipy.spatial.Delaunay | None:
    """Return source-space Delaunay, reusing the transform cache when present."""
    if isinstance(transform, ITriangulatedSourceSpace):
        try:
            tri = transform.source_space_trianglulation
        except Exception:
            tri = None
        if tri is not None and hasattr(tri, "find_simplex"):
            return tri
    if source_points.shape[0] < 3:
        return None
    return scipy.spatial.Delaunay(np.asarray(source_points, dtype=np.float64))


def source_to_target_mapper_for_interactive_drag(
        transform: nornir_imageregistration.ITransform,
) -> Callable[[NDArray[np.floating]], NDArray[np.floating]] | None:
    """Return a Source→Target mapper that does not rebuild interpolators or call Transform().

    Grid transforms use bilinear sampling of the live TargetPoints lattice. Other
    control-point transforms use the cached source-space Delaunay when available.
    """
    if not isinstance(transform, IControlPoints):
        return None
    target_points = nornir_imageregistration.EnsureNumpyArray(transform.TargetPoints)
    source_points = nornir_imageregistration.EnsureNumpyArray(transform.SourcePoints)
    if target_points.size == 0 or source_points.size == 0:
        return None
    if isinstance(transform, IGridTransform):
        dims = getattr(transform, 'grid_dims', None)
        if dims is None:
            dims = transform.grid.grid_dims
        ny, nx = int(dims[0]), int(dims[1])
        if ny * nx != target_points.shape[0]:
            return None
        source_grid = source_points.reshape(ny, nx, 2)
        target_grid = target_points.reshape(ny, nx, 2)
        axis_y = source_grid[:, 0, 0]
        axis_x = source_grid[0, :, 1]

        def _map_grid(query_yx: NDArray[np.floating]) -> NDArray[np.floating]:
            return _bilinear_sample_grid(query_yx, axis_y, axis_x, target_grid)

        return _map_grid

    delaunay = _source_space_delaunay(transform, source_points)
    if delaunay is None:
        return None

    def _map_mesh(query_yx: NDArray[np.floating]) -> NDArray[np.floating]:
        return barycentric_sample_delaunay(query_yx, delaunay, target_points)

    return _map_mesh


def patch_tile_vertices_from_control_points(
        vertices: NDArray[np.floating],
        mapper: Callable[[NDArray[np.floating]], NDArray[np.floating]],
) -> NDArray[np.floating] | None:
    """Update vertex Target XY from live control points; keep Source XY, Z, and UVs."""
    verts = np.array(vertices, dtype=np.float32, copy=True)
    if verts.ndim != 2 or verts.shape[1] < 5 or verts.shape[0] == 0:
        return None
    source_yx = np.column_stack((verts[:, 4], verts[:, 3])).astype(np.float64)
    target_yx = mapper(source_yx)
    if target_yx is None or target_yx.shape != source_yx.shape:
        return None
    if not np.all(np.isfinite(target_yx)):
        return None
    verts[:, 0] = target_yx[:, 1]
    verts[:, 1] = target_yx[:, 0]
    return verts


def try_patch_tile_vertices_from_control_points(
        render_data: TileGLObjects,
        mapper: Callable[[NDArray[np.floating]], NDArray[np.floating]],
) -> bool:
    """Patch an existing deformable tile mesh in place. Returns False to request remesh."""
    if render_data.is_rigid_quad or not render_data.mesh_populated:
        return False
    data = render_data.vertex_buffer.data
    if data is None:
        return False
    verts = np.asarray(data)
    if verts.ndim == 1:
        if verts.size % 8 != 0:
            return False
        verts = verts.reshape((-1, 8))
    patched = patch_tile_vertices_from_control_points(verts, mapper)
    if patched is None:
        return False
    render_data.vertex_buffer.data = patched
    return True


def _tile_vertices_as_nx8(data: Any) -> NDArray[np.floating] | None:
    """Return vertex buffer contents as (N, 8), or None when the layout is unusable."""
    if data is None:
        return None
    verts = np.asarray(data)
    if verts.ndim == 1:
        if verts.size % 8 != 0:
            return None
        verts = verts.reshape((-1, 8))
    if verts.ndim != 2 or verts.shape[1] < 5 or verts.shape[0] == 0:
        return None
    return verts


def patch_tile_vertices_from_stencil(
        vertices: NDArray[np.floating],
        cp_indices: NDArray[np.integer],
        cp_weights: NDArray[np.floating],
        target_points: NDArray[np.floating],
        source_points: NDArray[np.floating],
        moved_indices: NDArray[np.integer],
        edit_space: Space,
) -> tuple[NDArray[np.floating], NDArray[np.floating]] | None:
    """Patch Target XY from a cached barycentric stencil.

    Target-space edits blend live TargetPoints with cached weights. Source-space
    edits refresh weights from live SourcePoints when the query is still inside
    the last simplex; vertices that left the triangle are left unchanged.
    """
    verts = np.array(vertices, dtype=np.float32, copy=True)
    if verts.ndim != 2 or verts.shape[1] < 5 or verts.shape[0] == 0:
        return None
    indices = np.asarray(cp_indices)
    weights = np.asarray(cp_weights, dtype=np.float64)
    if indices.shape != (verts.shape[0], 3) or weights.shape != (verts.shape[0], 3):
        return None
    target = np.asarray(target_points, dtype=np.float64)
    source = np.asarray(source_points, dtype=np.float64)
    moved = np.unique(np.asarray(moved_indices, dtype=np.intp).ravel())
    if moved.size == 0:
        return verts, weights
    affected = np.any(np.isin(indices, moved), axis=1)
    if not np.any(affected):
        return verts, weights

    blend_mask = affected
    if edit_space == Space.Source:
        # Outside-hull stencils store nearest CP as (i, i, i). That triangle is
        # degenerate, so still-inside would skip them; snap to that CP instead.
        nearest = (indices[:, 0] == indices[:, 1]) & (indices[:, 1] == indices[:, 2])
        need_inside = affected & ~nearest
        still_inside = affected & nearest
        if np.any(need_inside):
            source_yx = np.column_stack((verts[:, 4], verts[:, 3])).astype(np.float64)
            tri = indices[need_inside]
            new_weights, inside = barycentric_weights_in_triangle(
                source_yx[need_inside],
                source[tri[:, 0]],
                source[tri[:, 1]],
                source[tri[:, 2]],
            )
            weights = np.array(weights, dtype=np.float64, copy=True)
            need_idx = np.flatnonzero(need_inside)
            still_inside[need_idx[inside]] = True
            weights[need_idx[inside]] = new_weights[inside]
        blend_mask = still_inside
        if not np.any(blend_mask):
            return verts, weights

    mapped = apply_barycentric_stencil(indices[blend_mask], weights[blend_mask], target)
    if mapped.shape[0] != int(np.count_nonzero(blend_mask)):
        return None
    if not np.all(np.isfinite(mapped)):
        return None
    verts[blend_mask, 0] = mapped[:, 1]
    verts[blend_mask, 1] = mapped[:, 0]
    return verts, weights


def try_patch_tile_vertices_from_stencil(
        render_data: TileGLObjects,
        target_points: NDArray[np.floating],
        source_points: NDArray[np.floating],
        moved_indices: NDArray[np.integer],
        edit_space: Space,
) -> bool:
    """Patch a mesh tile from its cached stencil. Returns False when no stencil exists."""
    if render_data.is_rigid_quad or not render_data.mesh_populated:
        return False
    if render_data.cp_indices is None or render_data.cp_weights is None:
        return False
    verts = _tile_vertices_as_nx8(render_data.vertex_buffer.data)
    if verts is None:
        return False
    patched = patch_tile_vertices_from_stencil(
        verts,
        render_data.cp_indices,
        render_data.cp_weights,
        target_points,
        source_points,
        moved_indices,
        edit_space,
    )
    if patched is None:
        return False
    new_verts, new_weights = patched
    render_data.vertex_buffer.data = new_verts
    render_data.cp_weights = new_weights
    return True


def tile_coords_for_control_points(image_height: int,
                                   image_width: int,
                                   texture_size: tuple[int, int],
                                   point_indices: NDArray[np.integer],
                                   transform: nornir_imageregistration.IControlPoints,
                                   halo: int = 1) -> set[tuple[int, int]]:
    """Return tile grid coordinates affected by moving the given control points."""
    tile_h, tile_w = int(texture_size[0]), int(texture_size[1])
    num_cols = int(np.ceil(image_width / float(tile_w)))
    num_rows = int(np.ceil(image_height / float(tile_h)))
    coords: set[tuple[int, int]] = set()
    target_pts = nornir_imageregistration.EnsureNumpyArray(transform.TargetPoints)
    source_pts = nornir_imageregistration.EnsureNumpyArray(transform.SourcePoints)
    n_points = min(target_pts.shape[0], source_pts.shape[0])

    def _add_tiles_for_yx(y: float, x: float) -> None:
        if not (np.isfinite(x) and np.isfinite(y)):
            return
        ix = int(x // tile_w)
        iy = int(y // tile_h)
        for dx in range(-halo, halo + 1):
            for dy in range(-halo, halo + 1):
                cx, cy = ix + dx, iy + dy
                if 0 <= cx < num_cols and 0 <= cy < num_rows:
                    coords.add((cx, cy))

    for idx in np.atleast_1d(point_indices):
        if idx < 0 or idx >= n_points:
            continue
        i = int(idx)
        _add_tiles_for_yx(target_pts[i, 0], target_pts[i, 1])
        _add_tiles_for_yx(source_pts[i, 0], source_pts[i, 1])
    return coords


def _tile_height_width(texture_size: tuple[int, int]) -> tuple[int, int] | None:
    """Return (tile_h, tile_w) or None when the texture grid size is unusable."""
    try:
        tile_h = int(texture_size[0])
        tile_w = int(texture_size[1])
    except (TypeError, ValueError, IndexError, OverflowError):
        return None
    if tile_h <= 0 or tile_w <= 0:
        return None
    return tile_h, tile_w


def _finite_rect_edges(
        visible_rect: nornir_imageregistration.Rectangle,
) -> tuple[float, float, float, float] | None:
    """Return (y0, x0, y1, x1) when every edge is finite; otherwise None."""
    with np.errstate(invalid='ignore', over='ignore', divide='ignore'):
        y0, x0 = visible_rect.BottomLeft
        height = float(visible_rect.Height)
        width = float(visible_rect.Width)
        y0_f = float(y0)
        x0_f = float(x0)
        if not all(np.isfinite(v) for v in (y0_f, x0_f, height, width)):
            return None
        return y0_f, x0_f, y0_f + height, x0_f + width


def tile_coords_for_visible_bounds(image_height: int,
                                   image_width: int,
                                   texture_size: tuple[int, int],
                                   visible_rect: nornir_imageregistration.Rectangle | None
                                   ) -> set[tuple[int, int]] | None:
    """Return tile coordinates intersecting visible_rect, or None to mean all tiles.

    None is also returned when *visible_rect* or tile size is non-finite or empty so
    callers skip culling instead of raising during paint.
    """
    if visible_rect is None:
        return None
    tile_hw = _tile_height_width(texture_size)
    if tile_hw is None:
        return None
    tile_h, tile_w = tile_hw
    edges = _finite_rect_edges(visible_rect)
    if edges is None:
        return None
    y0, x0, y1, x1 = edges
    num_cols = int(np.ceil(image_width / float(tile_w)))
    num_rows = int(np.ceil(image_height / float(tile_h)))
    ix0 = max(0, int(np.floor(x0 / float(tile_w))))
    ix1 = min(num_cols - 1, int(np.floor(max(x0, x1 - 1) / float(tile_w))))
    iy0 = max(0, int(np.floor(y0 / float(tile_h))))
    iy1 = min(num_rows - 1, int(np.floor(max(y0, y1 - 1) / float(tile_h))))
    coords: set[tuple[int, int]] = set()
    for ix in range(ix0, ix1 + 1):
        for iy in range(iy0, iy1 + 1):
            coords.add((ix, iy))
    return coords


def expand_visible_rectangle_by_tiles(
        visible_rect: nornir_imageregistration.Rectangle,
        texture_size: tuple[int, int],
        margin_tiles: int = 1,
) -> nornir_imageregistration.Rectangle:
    """Expand a visible rectangle by whole texture tiles on each side for prefetch."""
    if margin_tiles <= 0:
        return visible_rect
    tile_hw = _tile_height_width(texture_size)
    if tile_hw is None:
        return visible_rect
    tile_h, tile_w = tile_hw
    margin_y = float(margin_tiles * tile_h)
    margin_x = float(margin_tiles * tile_w)
    y0, x0 = visible_rect.BottomLeft
    y1 = y0 + visible_rect.Height
    x1 = x0 + visible_rect.Width
    return nornir_imageregistration.Rectangle.CreateFromBounds(
        np.array((y0 - margin_y, x0 - margin_x, y1 + margin_y, x1 + margin_x)))


def _tile_bounding_rect(
        grid_coords: tuple[int, int],
        texture_size: tuple[int, int]) -> nornir_imageregistration.spatial.Rectangle:
    """Return the axis-aligned tile rectangle in texture coordinates."""
    ix, iy = grid_coords
    x = texture_size[1] * ix
    y = texture_size[0] * iy
    return nornir_imageregistration.spatial.Rectangle.CreateFromPointAndArea((y, x), texture_size)


def _mesh_barycentric_stencil(
        vertices: NDArray[np.floating],
        transform: nornir_imageregistration.ITransform,
) -> tuple[NDArray[np.integer] | None, NDArray[np.floating] | None]:
    """Control-point stencil for deformable mesh tile vertices; None for grid/quads."""
    if isinstance(transform, IGridTransform):
        return None, None
    if not isinstance(transform, ITriangulatedSourceSpace):
        return None, None
    verts = np.asarray(vertices)
    if verts.ndim != 2 or verts.shape[1] < 5 or verts.shape[0] == 0:
        return None, None
    try:
        delaunay = transform.source_space_trianglulation
    except Exception:
        return None, None
    if delaunay is None or not hasattr(delaunay, "find_simplex"):
        return None, None
    source_yx = np.column_stack((verts[:, 4], verts[:, 3])).astype(np.float64)
    return barycentric_stencil_delaunay(source_yx, delaunay)


def _tile_mesh_cpu_entry(
        vertices: NDArray[np.floating],
        indices: NDArray[np.integer],
        simplices: NDArray[np.integer] | None,
        point_count: int,
        is_rigid_quad: bool,
        transform: nornir_imageregistration.ITransform | None = None,
):
    """Build a CPU tile entry, attaching a barycentric stencil for mesh tiles."""
    from pyre.controllers.tile_mesh_cache import TileMeshCpuEntry

    cp_indices = None
    cp_weights = None
    if not is_rigid_quad and transform is not None:
        cp_indices, cp_weights = _mesh_barycentric_stencil(vertices, transform)
    return TileMeshCpuEntry(
        vertices=vertices,
        indices=indices,
        simplices=simplices,
        point_count=point_count,
        is_rigid_quad=is_rigid_quad,
        cp_indices=cp_indices,
        cp_weights=cp_weights,
    )


def build_tile_mesh_cpu(transform: nornir_imageregistration.ITransform,
                        grid_coords: tuple[int, int],
                        texture_size: tuple[int, int],
                        image_space: Space,
                        cached_entry: TileGLObjects | None = None,
                        force_static_quads: bool = False,
                        extrapolate: bool = True):
    """Build CPU tile mesh (Delaunay CP mesh or static quad).

    :param force_static_quads: When True, emit identity tile quads even for mesh/grid
        transforms. Used for Target panels and standalone Source panels so moving
        TargetPoints cannot fold the displayed image.
    :param extrapolate: When False, skip mesh RBF fallback (avoids UI-thread weight solve).
    """
    if force_static_quads or is_rigid_transform(transform):
        tile_bounding_rect = _tile_bounding_rect(grid_coords, texture_size)
        verts, indices = _rigid_tile_quad_render_data(tile_bounding_rect, image_space)
        return _tile_mesh_cpu_entry(verts, indices, None, 4, True)

    tile_bounding_rect = _tile_bounding_rect(grid_coords, texture_size)
    if isinstance(transform, IGridTransform):
        grid_mesh = _grid_tile_mesh_point_pairs(transform, tile_bounding_rect)
        if grid_mesh is not None:
            pairs, simplices = grid_mesh
            vertarray = _render_data_with_cached_simplices(
                pairs, tile_bounding_rect, image_space, simplices,
                require_valid_topology=False)
            indices = simplices.flatten().astype(np.uint16)
            return _tile_mesh_cpu_entry(
                vertarray, indices, simplices, int(pairs.shape[0]), False, transform)

    all_point_pairs = collect_verticies_within_bounding_box(
        tile_bounding_rect, transform, image_space, extrapolate=extrapolate)
    point_count = all_point_pairs.shape[0]
    point_pairs_np = _point_pairs_to_numpy_f64(all_point_pairs)
    fixed_points_yx, warped_points_yx = np.hsplit(point_pairs_np, 2)
    texture_points = _texture_coordinates(
        warped_points_yx if image_space == Space.Source else fixed_points_yx,
        bounding_rect=tile_bounding_rect)

    if cached_entry is not None and cached_entry.cached_simplices is not None:
        if _simplices_compatible_with_points(
                cached_entry.cached_simplices, point_count, cached_entry.point_count):
            try:
                vertarray = _render_data_with_cached_simplices(
                    all_point_pairs, tile_bounding_rect, image_space, cached_entry.cached_simplices)
                indices = cached_entry.cached_simplices.flatten().astype(np.uint16)
                return _tile_mesh_cpu_entry(
                    vertarray, indices, cached_entry.cached_simplices, point_count, False,
                    transform)
            except ValueError:
                repaired = _repair_delaunay_by_edge_flips(texture_points, cached_entry.cached_simplices)
                if repaired is not None:
                    try:
                        vertarray = _render_data_with_cached_simplices(
                            all_point_pairs, tile_bounding_rect, image_space, repaired)
                        indices = repaired.flatten().astype(np.uint16)
                        return _tile_mesh_cpu_entry(
                            vertarray, indices, repaired, point_count, False, transform)
                    except ValueError:
                        pass

    tri = scipy.spatial.Delaunay(texture_points)
    simplices = tri.simplices.copy()
    vertarray = _render_data_with_cached_simplices(
        all_point_pairs, tile_bounding_rect, image_space, simplices)
    indices = simplices.flatten().astype(np.uint16)
    return _tile_mesh_cpu_entry(vertarray, indices, simplices, point_count, False, transform)


def apply_tile_mesh_cpu(render_data: TileGLObjects, entry) -> None:
    render_data.vertex_buffer.data = entry.vertices
    render_data.index_buffer.data = entry.indices
    render_data.cached_simplices = entry.simplices
    render_data.point_count = entry.point_count
    render_data.is_rigid_quad = entry.is_rigid_quad
    render_data.mesh_populated = True
    render_data.cp_indices = (
        None if entry.cp_indices is None else np.array(entry.cp_indices, copy=True))
    render_data.cp_weights = (
        None if entry.cp_weights is None else np.array(entry.cp_weights, copy=True))


def _update_tile_buffers(transform: nornir_imageregistration.ITransform,
                         grid_coords: tuple[int, int],
                         texture_size: tuple[int, int],
                         image_space: Space,
                         get_or_create_tile_globjects: Callable[[int, int], TileGLObjects | None],
                         shared_cpu_entry: 'TileMeshCpuEntry | None' = None,
                         force_static_quads: bool = False,
                         extrapolate: bool = True):
    """Create/Update the GL buffers for a given tile.
    :param get_or_create_tile_globjects: Function to get or create the TileGLObjects for a tile
    :param shared_cpu_entry: Optional precomputed CPU mesh from TileMeshCpuCache
    :param force_static_quads: Prefer identity quads when rebuilding without a shared entry
    :param extrapolate: Forwarded to mesh transform mapping (False avoids UI-thread RBF solve)
    """

    ix, iy = grid_coords
    render_data = get_or_create_tile_globjects(ix, iy)
    if render_data is None:
        return

    with timed(f'tile_buffer ({ix},{iy})'):
        if shared_cpu_entry is not None:
            apply_tile_mesh_cpu(render_data, shared_cpu_entry)
            return

        entry = build_tile_mesh_cpu(
            transform, grid_coords, texture_size, image_space,
            cached_entry=render_data, force_static_quads=force_static_quads,
            extrapolate=extrapolate)
        apply_tile_mesh_cpu(render_data, entry)


def _calculate_tile_render_data(transform: nornir_imageregistration.ITransform,
                                grid_coords: tuple[int, int],
                                texture_size: tuple[int, int],
                                space: Space,
                                *,
                                extrapolate: bool = True) -> tuple[NDArray[np.floating], NDArray[np.integer]]:
    """
    Given a grid coordinate, return the vertices and indices to render the tile.
    These are usually fed into a GLBuffer.
    """
    tile_bounding_rect = _tile_bounding_rect(grid_coords, texture_size)

    all_point_pairs = collect_verticies_within_bounding_box(
        bounding_box=tile_bounding_rect,
        transform=transform,
        image_space=space,
        extrapolate=extrapolate)

    vertarray, indicies = _render_data_for_transform_point_pairs(
        point_pairs=all_point_pairs,
        tile_bounding_rect=tile_bounding_rect,
        space=space)

    return vertarray, indicies


def collect_verticies_within_bounding_box(
        bounding_box: nornir_imageregistration.Rectangle,
        transform: nornir_imageregistration.ITransform,
        image_space: Space,
        *,
        extrapolate: bool = True) -> NDArray[np.floating]:
    """
    Given a bounding rectangle defined in the "space" parameter, return all vertices that we want to use for rendering.
    This should be the boundaries of the box, control points falling within the box, and
    a regular grid of points across the box to ensure any distortion from a non-linear transform
    is properly represented.
    :return: A Nx4 array of source and target points, this is the position of each point in both source and target space
    """
    grid_points = _tile_grid_points(bounding_box, grid_size=(8, 8))
    grid_point_pairs = _find_corresponding_points(
        transform,
        grid_points,
        forward_transform=False if image_space == Space.Target else True,
        extrapolate=extrapolate)

    if isinstance(transform, nornir_imageregistration.IControlPoints):
        if image_space == Space.Source:
            contained_control_points = transform.GetPointPairsInSourceRect(bounding_box)
        else:
            contained_control_points = transform.GetPointPairsInTargetRect(bounding_box)

        all_point_pairs = grid_point_pairs if contained_control_points is None else _merge_point_pairs_with_transform(
            grid_point_pairs,
            contained_control_points)
    else:
        return grid_point_pairs

    return all_point_pairs


def collect_vertex_locations_within_bounding_box_after_transformation(
        bounding_box: nornir_imageregistration.Rectangle,
        transform: nornir_imageregistration.ITransform,
        forward_transform: bool) \
        -> NDArray[np.floating]:
    """
    Given a bounding box rectangle, return all vertices that we want to use for rendering.
    This should be the boundaries of the box, control points falling within the box, and
    a regular grid of points across the box to ensure any distortion from a non-linear transform
    is properly represented.
    :return: A Nx4 array of fixed and warped points, this is the position of each point in both source and target space
    """
    grid_points = _tile_grid_points(bounding_box, grid_size=(8, 8))
    grid_point_pairs = _find_corresponding_points(transform, grid_points,
                                                  forward_transform=forward_transform)

    if isinstance(transform, nornir_imageregistration.IControlPoints):
        transform_points = transform.GetPointPairsInSourceRect(
            bounding_box) if forward_transform else transform.GetPointPairsInTargetRect(bounding_box)

        all_point_pairs = grid_point_pairs if transform_points is None else _merge_point_pairs_with_transform(
            grid_point_pairs,
            transform_points)
    else:
        return grid_point_pairs

    return all_point_pairs
