"""
Contains routines that divide a transform and image into tiles that fit into a GPU's texture size.
"""
import dataclasses
from typing import Any, Callable
import scipy.spatial
import scipy.spatial.distance
import numpy as np
from numpy.typing import NDArray
import nornir_imageregistration

from pyre.space import Space

from pyre.gl_engine import DynamicVAO, GLBuffer, GLIndexBuffer, ShaderVAO


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

    # WarpedCornersO = [[y, x],
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
    # WarpedCorners.append([ytemp + y, xtemp + x])

    # WarpedCorners = np.array(WarpedCorners, dtype=np.float32)

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


def _find_corresponding_points(transform: nornir_imageregistration.ITransform,
                               points: NDArray[np.floating],
                               forward_transform: bool) -> NDArray[np.floating]:
    """
    Map the points through the transform and return the results as a Nx4 array of matched fixed and warped points.

    """

    # Figure out where the corners of the texture belong 
    if forward_transform:
        fixed_points = points
        warped_points = transform.Transform(points)
    else:
        fixed_points = transform.InverseTransform(points)
        warped_points = points

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

    # This is a mess.  Transforms use the terminology Fixed & Warped to describe themselves.  The transform function moves the warped points into fixed space.
    points_b = transform_points
    if len(points_a) > 0 and len(points_b) > 0:
        all_point_pairs = np.vstack([points_a, points_b])
        unique_point_pairs = nornir_imageregistration.core.remove_duplicate_points(all_point_pairs, [1, 0])
        return unique_point_pairs

    if len(points_a) > 0:
        return points_a

    if len(points_b) > 0:
        return points_b


def _build_subtile_point_pairs(transform: nornir_imageregistration.ITransform,
                               rect: nornir_imageregistration.Rectangle,
                               forward_transform: bool = True, ) -> NDArray[np.floating]:
    """Determine transform points for a subregion of the transform"""
    tile_points = _tile_grid_points(rect)
    tile_point_pairs = _find_corresponding_points(transform, tile_points,
                                                  forward_transform=forward_transform)
    transform_point_pairs = np.concatenate(np.array(transform.GetWarpedPointsInRect(rect.ToArray())),
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


def _z_values_for_points_by_distance(points_yx: NDArray[np.floating]) -> NDArray[np.floating]:
    """
    :param points_yx:
    :return: A Z depth for each vertex, which is equal to the distance of the vertex from the center (average) of the points
    """
    center = np.mean(points_yx, 0)
    z = scipy.spatial.distance.cdist(np.resize(center, (1, 2)), points_yx, 'euclidean')
    z = np.transpose(z)
    z /= np.max(z)
    z = 1 - z
    return z


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
     return the texture coordinates for each point
    :param points_yx: Points to generate texture coordinates for
    :param bounding_rect: Bounding rectangle for the texture space
    :return: texture coordinates for a rectangle in fixed (source) space
    """
    texture_points = (points_yx - np.array(bounding_rect.BottomLeft)) / bounding_rect.Size

    # Need to convert texture coordinates to X,Y coordinates
    texture_points = np.fliplr(texture_points)
    return texture_points


def _render_data_for_transform_point_pairs(point_pairs: NDArray[np.floating],
                                           tile_bounding_rect: nornir_imageregistration.Rectangle,
                                           space: Space,
                                           z: float | None = None,
                                           ) -> tuple[NDArray[np.floating], NDArray[np.uint16]]:
    """
    Generate verticies (source, target and texture coordinates) for a set of transform points and the
    indicies to render them as triangles
    :return: Verts3D, indicies, Verts3d is Source (X,Y,Z), Target (X,Y,Z), Texture (U,V)
    """

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


def _update_tile_buffers(transform: nornir_imageregistration.ITransform,
                         grid_coords: tuple[int, int],
                         texture_size: tuple[int, int],
                         image_space: Space,
                         get_or_create_tile_globjects: Callable[[int, int], TileGLObjects]):
    """Create/Update the GL buffers for a given tile.
    :param get_or_create_tile_globjects: Function to get or create the TileGLObjects for a tile
    """

    vertarray, indicies = _calculate_tile_render_data(transform, grid_coords, texture_size, image_space)

    if vertarray is None or vertarray.shape[0] == 0:
        raise ValueError("No elements in vertex array object")

    ix, iy = grid_coords
    render_data = get_or_create_tile_globjects(ix, iy)
    render_data.vertex_buffer.data = vertarray
    render_data.index_buffer.data = indicies


def _calculate_tile_render_data(transform: nornir_imageregistration.ITransform,
                                grid_coords: tuple[int, int],
                                texture_size: tuple[int, int],
                                space: Space) -> tuple[NDArray[np.floating], NDArray[np.integer]]:
    """
    Given a grid coordinate, return the verticies and indicies to render the tile.
    These are usually fed into a GLBuffer.
    """
    ix, iy = grid_coords
    x = texture_size[1] * ix
    y = texture_size[0] * iy

    tile_bounding_rect = nornir_imageregistration.spatial.Rectangle.CreateFromPointAndArea((y, x),
                                                                                           texture_size)

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
    Given a bounding rectangle defined in the "space" parameter, return all verticies that we want to use for rendering.
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
    Given a bounding box rectangle, return all verticies that we want to use for rendering.
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
