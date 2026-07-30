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
from nornir_imageregistration.transforms.base import IRigidTransform
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


def _points_to_numpy_f32(points: NDArray[np.floating]) -> NDArray[np.floating]:
    """Convert transform output (NumPy or CuPy) to NumPy float32 for GL/Qt paths."""
    try:
        import cupy as cp
    except ImportError:
        return np.asarray(points, dtype=np.float32)
    if cp.get_array_module(points) is cp:
        return np.asarray(cp.asnumpy(points), dtype=np.float32)
    return np.asarray(points, dtype=np.float32)


def _point_pairs_to_numpy_f64(point_pairs: NDArray[np.floating]) -> NDArray[np.floating]:
    """Host float64 point pairs for scipy.Delaunay / OpenGL mesh build (CuPy -> NumPy)."""
    if hasattr(point_pairs, 'get'):
        point_pairs = point_pairs.get()  # type: ignore[union-attr]
    return np.asarray(point_pairs, dtype=np.float64)


def _find_corresponding_points(transform: nornir_imageregistration.ITransform,
                               points: NDArray[np.floating],
                               forward_transform: bool) -> NDArray[np.floating]:
    """
    Map the points through the transform and return the results as a Nx4 array of matched fixed and warped points.

    """

    # Figure out where the corners of the texture belong
    pts_for_transform = nornir_imageregistration.EnsurePointsAre2DArray(points)
    if forward_transform:
        fixed_points = _points_to_numpy_f32(points)
        warped_points = _points_to_numpy_f32(transform.Transform(pts_for_transform))
    else:
        warped_points = _points_to_numpy_f32(points)
        fixed_points = _points_to_numpy_f32(transform.InverseTransform(pts_for_transform))

    return np.hstack((warped_points, fixed_points))


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
        all_point_pairs = np.vstack([points_a, points_b])
        unique_point_pairs = nornir_imageregistration.core.remove_duplicate_points(all_point_pairs, [1, 0])
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
    artifacts (noise at tile boundaries) when filtering with LINEAR or MIPMAP.
    Coordinates are inset so we never sample exactly on 0 or 1, reducing visible seams
    between adjacent tiles at low zoom.
    :param points_yx: Points to generate texture coordinates for
    :param bounding_rect: Bounding rectangle for the texture space
    :return: texture coordinates for a rectangle in fixed (source) space
    """
    # Ensure numpy: transform may return CuPy arrays; mixing with np.array() causes TypeError
    points_yx = np.asarray(points_yx, dtype=np.float64)
    size = np.array(bounding_rect.Size, dtype=np.float64)
    # +0.5 so the first texel center is at (0.5/w, 0.5/h) instead of sampling at (0,0) edge
    texture_points = (points_yx - np.array(bounding_rect.BottomLeft) + 0.5) / size
    # Keep UVs strictly inside [0,1] by a half-texel inset to avoid sampling tile edges
    # (shared boundaries between tiles can produce seams with CLAMP_TO_BORDER at low zoom)
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
                                       z: float | None = None) -> NDArray[np.floating]:
    point_pairs = _point_pairs_to_numpy_f64(point_pairs)
    fixed_points_yx, warped_points_yx = np.hsplit(point_pairs, 2)
    texture_points = _texture_coordinates(
        warped_points_yx if space == Space.Source else fixed_points_yx,
        bounding_rect=tile_bounding_rect)
    if not _topology_still_valid(texture_points, simplices):
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


def tile_coords_for_visible_bounds(image_height: int,
                                   image_width: int,
                                   texture_size: tuple[int, int],
                                   visible_rect: nornir_imageregistration.Rectangle | None
                                   ) -> set[tuple[int, int]] | None:
    """Return tile coordinates intersecting visible_rect, or None to mean all tiles."""
    if visible_rect is None:
        return None
    tile_h, tile_w = int(texture_size[0]), int(texture_size[1])
    num_cols = int(np.ceil(image_width / float(tile_w)))
    num_rows = int(np.ceil(image_height / float(tile_h)))
    y0, x0 = visible_rect.BottomLeft
    y1 = y0 + visible_rect.Height
    x1 = x0 + visible_rect.Width
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
    tile_h, tile_w = int(texture_size[0]), int(texture_size[1])
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


def build_tile_mesh_cpu(transform: nornir_imageregistration.ITransform,
                        grid_coords: tuple[int, int],
                        texture_size: tuple[int, int],
                        image_space: Space,
                        cached_entry: TileGLObjects | None = None,
                        force_static_quads: bool = False):
    """Build CPU tile mesh (Delaunay CP mesh or static quad).

    :param force_static_quads: When True, emit identity tile quads even for mesh/grid
        transforms. Used for Target panels and standalone Source panels so moving
        TargetPoints cannot fold the displayed image.
    """
    from pyre.controllers.tile_mesh_cache import TileMeshCpuEntry

    if force_static_quads or is_rigid_transform(transform):
        tile_bounding_rect = _tile_bounding_rect(grid_coords, texture_size)
        verts, indices = _rigid_tile_quad_render_data(tile_bounding_rect, image_space)
        return TileMeshCpuEntry(vertices=verts, indices=indices, simplices=None,
                                point_count=4, is_rigid_quad=True)

    vertarray, indices = _calculate_tile_render_data(transform, grid_coords, texture_size, image_space)
    simplices = None
    point_count = 0
    if cached_entry is not None and cached_entry.cached_simplices is not None:
        try:
            tile_bounding_rect = _tile_bounding_rect(grid_coords, texture_size)
            all_point_pairs = collect_verticies_within_bounding_box(tile_bounding_rect, transform, image_space)
            point_count = all_point_pairs.shape[0]
            if _simplices_compatible_with_points(
                    cached_entry.cached_simplices, point_count, cached_entry.point_count):
                simplices = cached_entry.cached_simplices
                vertarray = _render_data_with_cached_simplices(
                    all_point_pairs, tile_bounding_rect, image_space, simplices)
                indices = simplices.flatten().astype(np.uint16)
                return TileMeshCpuEntry(vertices=vertarray, indices=indices, simplices=simplices,
                                        point_count=point_count, is_rigid_quad=False)
        except ValueError:
            pass

    tile_bounding_rect = _tile_bounding_rect(grid_coords, texture_size)
    all_point_pairs = collect_verticies_within_bounding_box(tile_bounding_rect, transform, image_space)
    point_count = all_point_pairs.shape[0]
    point_pairs_np = _point_pairs_to_numpy_f64(all_point_pairs)
    fixed_points_yx, warped_points_yx = np.hsplit(point_pairs_np, 2)
    texture_points = _texture_coordinates(
        warped_points_yx if image_space == Space.Source else fixed_points_yx,
        bounding_rect=tile_bounding_rect)

    if cached_entry is not None and cached_entry.cached_simplices is not None:
        if _simplices_compatible_with_points(
                cached_entry.cached_simplices, point_count, cached_entry.point_count):
            repaired = _repair_delaunay_by_edge_flips(texture_points, cached_entry.cached_simplices)
            if repaired is not None:
                try:
                    vertarray = _render_data_with_cached_simplices(
                        all_point_pairs, tile_bounding_rect, image_space, repaired)
                    indices = repaired.flatten().astype(np.uint16)
                    return TileMeshCpuEntry(vertices=vertarray, indices=indices, simplices=repaired,
                                            point_count=point_count, is_rigid_quad=False)
                except ValueError:
                    pass

    tri = scipy.spatial.Delaunay(texture_points)
    simplices = tri.simplices.copy()
    vertarray = _render_data_with_cached_simplices(
        all_point_pairs, tile_bounding_rect, image_space, simplices)
    indices = simplices.flatten().astype(np.uint16)
    return TileMeshCpuEntry(vertices=vertarray, indices=indices, simplices=simplices,
                            point_count=point_count, is_rigid_quad=False)


def apply_tile_mesh_cpu(render_data: TileGLObjects, entry) -> None:
    render_data.vertex_buffer.data = entry.vertices
    render_data.index_buffer.data = entry.indices
    render_data.cached_simplices = entry.simplices
    render_data.point_count = entry.point_count
    render_data.is_rigid_quad = entry.is_rigid_quad
    render_data.mesh_populated = True


def _update_tile_buffers(transform: nornir_imageregistration.ITransform,
                         grid_coords: tuple[int, int],
                         texture_size: tuple[int, int],
                         image_space: Space,
                         get_or_create_tile_globjects: Callable[[int, int], TileGLObjects | None],
                         shared_cpu_entry: 'TileMeshCpuEntry | None' = None,
                         force_static_quads: bool = False):
    """Create/Update the GL buffers for a given tile.
    :param get_or_create_tile_globjects: Function to get or create the TileGLObjects for a tile
    :param shared_cpu_entry: Optional precomputed CPU mesh from TileMeshCpuCache
    :param force_static_quads: Prefer identity quads when rebuilding without a shared entry
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
            cached_entry=render_data, force_static_quads=force_static_quads)
        apply_tile_mesh_cpu(render_data, entry)


def _calculate_tile_render_data(transform: nornir_imageregistration.ITransform,
                                grid_coords: tuple[int, int],
                                texture_size: tuple[int, int],
                                space: Space) -> tuple[NDArray[np.floating], NDArray[np.integer]]:
    """
    Given a grid coordinate, return the vertices and indices to render the tile.
    These are usually fed into a GLBuffer.
    """
    tile_bounding_rect = _tile_bounding_rect(grid_coords, texture_size)

    all_point_pairs = collect_verticies_within_bounding_box(
        bounding_box=tile_bounding_rect,
        transform=transform,
        image_space=space)

    vertarray, indicies = _render_data_for_transform_point_pairs(
        point_pairs=all_point_pairs,
        tile_bounding_rect=tile_bounding_rect,
        space=space)

    return vertarray, indicies


def collect_verticies_within_bounding_box(
        bounding_box: nornir_imageregistration.Rectangle,
        transform: nornir_imageregistration.ITransform,
        image_space: Space) -> NDArray[np.floating]:
    """
    Given a bounding rectangle defined in the "space" parameter, return all vertices that we want to use for rendering.
    This should be the boundaries of the box, control points falling within the box, and
    a regular grid of points across the box to ensure any distortion from a non-linear transform
    is properly represented.
    :return: A Nx4 array of source and target points, this is the position of each point in both source and target space
    """
    grid_points = _tile_grid_points(bounding_box, grid_size=(8, 8))
    grid_point_pairs = _find_corresponding_points(transform,
                                                  grid_points,
                                                  forward_transform=False if image_space == Space.Target else True)

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
