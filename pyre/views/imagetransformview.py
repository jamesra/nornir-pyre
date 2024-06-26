"""
Created on Oct 19, 2012

@author: u0490822
"""

# from imageop import scale
from numpy.typing import NDArray
import scipy.spatial
import scipy.spatial.distance
import numpy as np
import dataclasses
from typing import Any, Generator, Callable
import warnings

import wx.glcanvas

import nornir_imageregistration
import nornir_imageregistration.transforms.base
import nornir_imageregistration.transforms.triangulation

import OpenGL.GL as gl
from OpenGL.arrays import vbo
import pyre
from pyre.space import Space
import pyre.gl_engine.shaders as shaders
from pyre.gl_engine import ShaderVAO, DynamicVAO, GLBuffer, GLIndexBuffer
from pyre.resources import point_textures
from pyre.views.controlpoint_view import ControlPointView
from pyre.views.interfaces import IImageTransformView
from pyre.state.gl_context_manager import IGLContextManager


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


class ImageTransformView(IImageTransformView):
    """
    Combines an image and a transform to render an image.
    Images are divided into a grid of tiles.  Tiles are sized
    to fit within texture memory limits of the GPU.
    Read-only operations used for rendering the graphics.
    """

    rendercache: RenderCache | None  # The cache of rendered data
    _z: float
    _image_viewmodel: pyre.viewmodels.ImageViewModel
    _image_mask_viewmodel: pyre.viewmodels.ImageViewModel | None
    _transform_controller: pyre.viewmodels.TransformController = None
    Debug: bool
    _gl_initialized: bool = False
    _tile_render_data: RenderDataMap
    _image_space: Space  # The space the image is in
    _activate_context: Callable[
        [], None]  # A function we can call to ensure the view's GL context is current, must be used before creating GL Objects

    @property
    def width(self) -> int:
        if self._image_viewmodel is None:
            return 1

        return self._image_viewmodel.width

    @property
    def height(self) -> int:
        if self._image_viewmodel is None:
            return 1

        return self._image_viewmodel.height

    @property
    def image_view_model(self) -> pyre.viewmodels.ImageViewModel:
        return self._image_viewmodel

    @image_view_model.setter
    def image_view_model(self, value: pyre.viewmodels.ImageViewModel):
        self._image_viewmodel = value
        if value is not None:
            self.create_objects()

    @property
    def image_mask_view_model(self) -> pyre.viewmodels.ImageViewModel | None:
        return self._image_mask_viewmodel

    @property
    def transform(self) -> nornir_imageregistration.ITransform:
        return self._transform_controller.TransformModel

    @property
    def transform_controller(self) -> pyre.viewmodels.TransformController:
        return self._transform_controller

    @transform_controller.setter
    def transform_controller(self, value: pyre.viewmodels.TransformController):
        if self._transform_controller is not None:
            self._transform_controller.RemoveOnChangeEventListener(self.OnTransformChanged)

        self._transform_controller = value

        if value is not None:
            if not isinstance(value, pyre.viewmodels.TransformController):
                raise ValueError(f"Expected _transform_controller type, got {value}")
            self._transform_controller.AddOnChangeEventListener(self.OnTransformChanged)

        self.OnTransformChanged(value)

    @property
    def z(self) -> float:
        return self._z

    @z.setter
    def z(self, value: float):
        self._z = value

    def __init__(self,
                 space: Space,
                 activate_context: Callable[[], None],
                 image_view_model: pyre.viewmodels.ImageViewModel | None = None,
                 image_mask_view_model: pyre.viewmodels.ImageViewModel | None = None,
                 transform_controller: pyre.viewmodels.TransformController | None = None,
                 ):
        """
        Constructor
        :param imageviewmodel image_view_model: Textures for image
        :param transform transform_controller: nornir_imageregistration transform
        """
        self._activate_context = activate_context
        self._tile_render_data = {}
        self._image_space = space
        self.rendercache = RenderCache()
        self._image_viewmodel = image_view_model
        self._image_mask_viewmodel = image_mask_view_model
        self._transform_controller = transform_controller
        self._z = 0.5

        self._transform_controller.AddOnChangeEventListener(self.OnTransformChanged)

        self.Debug = False

        self.create_objects()

    def create_objects(self):
        """Initialize GL objects"""
        if not self._gl_initialized:
            self._gl_initialized = True

        self.update_all_tile_buffers()

    def OnTransformChanged(self, transform_controller: pyre.viewmodels.TransformController):
        if self._gl_initialized:
            self.update_all_tile_buffers()

    def update_all_tile_buffers(self):
        """Update the buffers for all tiles in the image viewmodel"""
        unused_grid_coords = set(self._tile_render_data.keys())

        self._activate_context()

        if self._image_viewmodel is not None:
            for grid_coords in self._image_viewmodel.generate_grid_indicies():
                self._update_tile_buffers(grid_coords, self._image_viewmodel, self._image_space)
                if grid_coords in unused_grid_coords:
                    unused_grid_coords.remove(grid_coords)

        for grid_coord in unused_grid_coords:
            del self._tile_render_data[grid_coord]

    def draw_lines(self, draw_in_fixed_space: bool):
        """
        :param bool draw_in_fixed_space: True if lines should be drawn in fixed space.  Otherwise draw in warped space
        """
        if self.transform is None:
            return

        Triangles = []
        if not draw_in_fixed_space:
            if not isinstance(self.transform, nornir_imageregistration.transforms.ITriangulatedSourceSpace):
                return

            # Triangles = self.__Transform.WarpedTriangles
            verts = np.fliplr(self.transform.SourcePoints)
            Triangles = self.transform.source_space_trianglulation
        else:
            if not isinstance(self.transform, nornir_imageregistration.transforms.ITriangulatedTargetSpace):
                return

            verts = np.fliplr(self.transform.TargetPoints)
            Triangles = self.transform.target_space_trianglulation

        if verts is not None and Triangles is not None:
            pyre.views.DrawTriangles(verts, Triangles)

    @classmethod
    def _tile_grid_points(cls, tile_bounding_rect: nornir_imageregistration.Rectangle,
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
        WarpedCorners = np.zeros(((grid_size[0] + 1) * (grid_size[1] + 1), 2), dtype=np.float32)

        xstep = int(w / grid_size[1])
        ystep = int(h / grid_size[0])

        for iX in range(0, grid_size[1] + 1):
            for iY in range(0, grid_size[0] + 1):
                WarpedCorners[(iX * (grid_size[0] + 1)) + iY] = (y + (iY * ystep), x + (iX * xstep))

        # for xtemp in range(0, w + 1, xstep):
        # for ytemp in range(0, h + 1, ystep):
        # WarpedCorners.append([ytemp + y, xtemp + x])

        # WarpedCorners = np.array(WarpedCorners, dtype=np.float32)

        return WarpedCorners

    @classmethod
    def _tile_bounding_points(cls, tile_bounding_rect: nornir_imageregistration.Rectangle,
                              grid_size: tuple[int, int] = (3, 3)) -> NDArray[np.floating]:
        """
        :return: Returns a set of point pairs mapping the boundaries of the image tile
        """

        (y, x) = tile_bounding_rect.BottomLeft
        h = int(tile_bounding_rect.Height)
        w = int(tile_bounding_rect.Width)

        WarpedCorners = [[y, x],
                         [y, x + w, ],
                         [y + h, x],
                         [y + h, x + w]]

        xstep = w // grid_size[1]
        ystep = h // grid_size[0]

        for ytemp in range(0, h + 1, int(ystep)):
            WarpedCorners.append([ytemp + y, 0 + x])
            WarpedCorners.append([ytemp + y, w + x])

        for xtemp in range(1, w, int(xstep)):
            WarpedCorners.append([0 + y, xtemp + x])
            WarpedCorners.append([h + y, xtemp + x])

        WarpedCorners = np.array(WarpedCorners, dtype=np.float32)

        return WarpedCorners

    @staticmethod
    def _find_corresponding_points(Transform: nornir_imageregistration.ITransform,
                                   Points: NDArray[np.floating],
                                   ForwardTransform: bool) -> NDArray[np.floating]:
        """
        Map the points through the transform and return the results as a Nx4 array of matched fixed and warped points.

        """

        # Figure out where the corners of the texture belong 
        if ForwardTransform:
            FixedPoints = Points
            WarpedPoints = Transform.Transform(Points)
        else:
            FixedPoints = Transform.InverseTransform(Points)
            WarpedPoints = Points

        return np.hstack((WarpedPoints, FixedPoints))

    @classmethod
    def _tile_bounding_rect(cls, Transform: nornir_imageregistration.ITransform,
                            tile_bounding_rect: nornir_imageregistration.Rectangle,
                            ForwardTransform: bool = True,
                            grid_size: tuple[int, int] = (3, 3)) -> nornir_imageregistration.Rectangle:
        """
        :return: Returns a bounding rectangle built from points placed around the edge of the tile
        """
        BorderPoints = cls._tile_bounding_points(tile_bounding_rect=tile_bounding_rect, grid_size=grid_size)
        BorderPointPairs = cls._find_corresponding_points(Transform, BorderPoints, ForwardTransform=ForwardTransform)
        return nornir_imageregistration.spatial.Rectangle.CreateFromBounds(
            nornir_imageregistration.spatial.BoundsArrayFromPoints(BorderPointPairs[:, 0:2]))

    @classmethod
    def _merge_point_pairs_with_transform(cls, PointsA: NDArray[np.floating],
                                          TransformPoints: NDArray[np.floating]) -> NDArray[np.floating]:
        """
        Extracts control points from a transform, merges them with the input points, and returns the result.
        Removes duplicates.
        :param PointsA:
        :param TransformPoints:
        :return:
        """

        # This is a mess.  Transforms use the terminology Fixed & Warped to describe themselves.  The transform function moves the warped points into fixed space.
        PointsB = TransformPoints
        if len(PointsA) > 0 and len(PointsB) > 0:
            AllPointPairs = np.vstack([PointsA, PointsB])
            unique_point_pairs = nornir_imageregistration.core.remove_duplicate_points(AllPointPairs, [1, 0])
            return unique_point_pairs

        if len(PointsA) > 0:
            return PointsA

        if len(PointsB) > 0:
            return PointsB

    @classmethod
    def _build_subtile_point_pairs(cls, Transform: nornir_imageregistration.ITransform,
                                   z: float,
                                   rect: nornir_imageregistration.Rectangle,
                                   ForwardTransform: bool = True, ) -> NDArray[np.floating]:
        """Determine transform points for a subregion of the transform"""

        TilePoints = cls._tile_grid_points(rect)
        TilePointPairs = cls._find_corresponding_points(Transform, TilePoints, ForwardTransform=ForwardTransform)
        TransformPointPairs = np.concatenate(np.array(Transform.GetWarpedPointsInRect(rect.ToArray())),
                                             2).squeeze()
        AllPointPairs = cls._merge_point_pairs(TilePointPairs, TransformPointPairs)

        return AllPointPairs

    @classmethod
    def _build_tile_point_pairs(cls, Transform: nornir_imageregistration.ITransform,
                                rect: nornir_imageregistration.Rectangle,
                                ForwardTransform: bool = True, ) -> NDArray[np.floating]:
        """
        Determine transform points the live within the bounding rectangle, adding points around the boundary of the bounding rectangle to the result set.
        """

        BorderPoints = cls._tile_bounding_points(rect)
        BorderPointPairs = cls._find_corresponding_points(Transform, BorderPoints, ForwardTransform=ForwardTransform)
        if isinstance(Transform, nornir_imageregistration.IControlPoints):
            AllPointPairs = cls._merge_point_pairs_with_transform(BorderPointPairs, Transform.points)
            return AllPointPairs
        else:
            return BorderPointPairs

    @classmethod
    def _z_values_for_points_by_distance(cls, PointsYX: NDArray[np.floating]) -> NDArray[np.floating]:
        """
        :param PointsYX:
        :return: A Z depth for each vertex, which is equal to the distance of the vertex from the center (average) of the points
        """
        center = np.mean(PointsYX, 0)
        Z = scipy.spatial.distance.cdist(np.resize(center, (1, 2)), PointsYX, 'euclidean')
        Z = np.transpose(Z)
        Z /= np.max(Z)
        Z = 1 - Z
        return Z

    @classmethod
    def _z_values_for_points_by_texture(cls, texture_points: NDArray[np.floating]) -> NDArray[np.floating]:
        """
        :param PointsYX:
        :return: A Z depth for each vertex, which is equal to the distance of the vertex from the center (average) of the points
        """
        centered_points = texture_points - 0.5
        z = np.power(centered_points, 2).sum(axis=1)
        z = np.sqrt(z)
        return z

    @classmethod
    def _texture_coordinates(cls, points_yx: NDArray[np.floating],
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

    @classmethod
    def _render_data_for_transform_point_pairs(cls,
                                               point_pairs: NDArray[np.floating],
                                               tile_bounding_rect: nornir_imageregistration.Rectangle,
                                               space: pyre.space.Space,
                                               z: float | None = None,
                                               ) -> tuple[NDArray[np.floating], NDArray[np.uint16]]:
        """
        Generate verticies (source, target and texture coordinates) for a set of transform points and the
        indicies to render them as triangles
        :return: Verts3D, indicies, Verts3d is Source (X,Y,Z), Target (X,Y,Z), Texture (U,V)
        """

        FixedPointsYX, WarpedPointsYX = np.hsplit(point_pairs, 2)

        # tile_bounding_rect = nornir_imageregistration.spatial.BoundingPrimitiveFromPoints(SourcePoints)
        # Need to convert from Y,x to X,Y coordinates
        FixedPointsXY = np.fliplr(FixedPointsYX)
        WarpedPointsXY = np.fliplr(WarpedPointsYX)
        # Do triangulation before we transform the points to prevent concave edges having a texture mapped over them.

        # texturePoints = (FixedPointsXY - np.array((x,y))) / np.array((w,h))

        texture_points = cls._texture_coordinates(WarpedPointsYX if space == Space.Source else FixedPointsYX,
                                                  bounding_rect=tile_bounding_rect)
        # print(str(texturePoints[0, :]))
        tri = scipy.spatial.Delaunay(texture_points)
        # np.array([[(u - x) / float(w), (v - y) / float(h)] for u, v in FixedPointsXY], dtype=np.float32)

        # Set vertex z according to distance from center
        if z is not None:
            z_array = np.ones((FixedPointsYX.shape[0], 1)) * z
        else:
            z_array = cls._z_values_for_points_by_texture(texture_points)

        verts3d = np.vstack((FixedPointsYX[:, 1],
                             FixedPointsYX[:, 0],
                             z_array.flat,
                             WarpedPointsYX[:, 1],
                             WarpedPointsYX[:, 0],
                             z_array.flat,
                             texture_points[:, 0],
                             texture_points[:, 1])).T

        verts3d = verts3d.astype(np.float32)

        indicies = tri.simplices.flatten().astype(np.uint16)

        return verts3d, indicies

    def _update_tile_buffers(self,
                             grid_coords: tuple[int, int],
                             image_view_model: pyre.viewmodels.ImageViewModel,
                             image_space: Space):
        """Update the GL buffers for a given tile"""
        ix, iy = grid_coords
        x = image_view_model.TextureSize[1] * ix
        y = image_view_model.TextureSize[0] * iy

        tile_bounding_rect = nornir_imageregistration.spatial.Rectangle.CreateFromPointAndArea((y, x),
                                                                                               image_view_model.TextureSize)

        all_point_pairs = ImageTransformView.collect_verticies_within_bounding_box(
            bounding_box=tile_bounding_rect,
            transform=self.transform,
            image_space=image_space)

        vertarray, indicies = ImageTransformView._render_data_for_transform_point_pairs(
            point_pairs=all_point_pairs,
            tile_bounding_rect=tile_bounding_rect,
            space=image_space)

        if vertarray is None or vertarray.shape[0] == 0:
            raise ValueError("No elements in vertex array object")

        render_data = self.get_or_create_tile_globjects(ix, iy)
        render_data.vertex_buffer.data = vertarray
        render_data.index_buffer.data = indicies

    def _calculate_tile_render_data(self,
                                    grid_coords: tuple[int, int],
                                    image_view_model: pyre.viewmodels.ImageViewModel,
                                    space: Space) -> tuple[NDArray[np.floating], NDArray[np.integer]]:
        """Given a grid coordinate, return the verticies and indicies to render the tile"""
        ix, iy = grid_coords
        x = image_view_model.TextureSize[1] * ix
        y = image_view_model.TextureSize[0] * iy

        tile_bounding_rect = nornir_imageregistration.spatial.Rectangle.CreateFromPointAndArea((y, x),
                                                                                               image_view_model.TextureSize)

        all_point_pairs = ImageTransformView.collect_verticies_within_bounding_box(
            bounding_box=tile_bounding_rect,
            transform=self.transform,
            image_space=space)

        vertarray, indicies = ImageTransformView._render_data_for_transform_point_pairs(
            point_pairs=all_point_pairs,
            tile_bounding_rect=tile_bounding_rect,
            space=space)

        return vertarray, indicies

    def _create_tile_globjects(self) -> TileGLObjects:
        """Create buffers and populate them with the vertex and index data"""

        # Generate the buffers for the VAO
        vertex_buffer = GLBuffer(layout=shaders.texture_shader.vertex_layout,
                                 usage=gl.GL_DYNAMIC_DRAW)

        index_buffer = GLIndexBuffer(usage=gl.GL_DYNAMIC_DRAW)

        vertex_array_object = DynamicVAO()
        vertex_array_object.begin_init()
        vertex_array_object.add_buffer(vertex_buffer)
        vertex_array_object.add_index_buffer(index_buffer)
        vertex_array_object.end_init()

        return TileGLObjects(vertex_buffer=vertex_buffer, index_buffer=index_buffer, vao=vertex_array_object)

    def get_or_create_tile_globjects(self, ix: int, iy: int):
        """Return the tile buffers for a grid coordinate, creating them if they do not exist"""
        if (ix, iy) not in self._tile_render_data:
            self._tile_render_data[(ix, iy)] = self._create_tile_globjects()

        return self._tile_render_data[(ix, iy)]

    @staticmethod
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
        GridPoints = ImageTransformView._tile_grid_points(bounding_box, grid_size=(8, 8))
        GridPointPairs = ImageTransformView._find_corresponding_points(transform,
                                                                       GridPoints,
                                                                       ForwardTransform=False if image_space == Space.Target else True)

        if isinstance(transform, nornir_imageregistration.IControlPoints):
            if image_space == Space.Source:
                contained_control_points = transform.GetPointPairsInSourceRect(bounding_box)
            else:
                contained_control_points = transform.GetPointPairsInTargetRect(bounding_box)

            AllPointPairs = GridPointPairs if contained_control_points is None else ImageTransformView._merge_point_pairs_with_transform(
                GridPointPairs,
                contained_control_points)
        else:
            return GridPointPairs

        return AllPointPairs

    @staticmethod
    def collect_vertex_locations_within_bounding_box_after_transformation(
            bounding_box: nornir_imageregistration.Rectangle,
            transform: nornir_imageregistration.ITransform,
            ForwardTransform: bool) \
            -> NDArray[np.floating]:
        """
        Given a bounding box rectangle, return all verticies that we want to use for rendering.
        This should be the boundaries of the box, control points falling within the box, and
        a regular grid of points across the box to ensure any distortion from a non-linear transform
        is properly represented.
        :return: A Nx4 array of fixed and warped points, this is the position of each point in both source and target space
        """
        GridPoints = ImageTransformView._tile_grid_points(bounding_box, grid_size=(8, 8))
        GridPointPairs = ImageTransformView._find_corresponding_points(transform, GridPoints,
                                                                       ForwardTransform=ForwardTransform)

        if isinstance(transform, nornir_imageregistration.IControlPoints):
            TransformPoints = transform.GetPointPairsInSourceRect(
                bounding_box) if ForwardTransform else transform.GetPointPairsInTargetRect(bounding_box)

            AllPointPairs = GridPointPairs if TransformPoints is None else ImageTransformView._merge_point_pairs_with_transform(
                GridPointPairs,
                TransformPoints)
        else:
            return GridPointPairs

        return AllPointPairs

    def draw(self,
             view_proj: NDArray[np.floating],
             space: pyre.Space,
             bounding_box: nornir_imageregistration.Rectangle | None = None):

        if self._image_viewmodel is None:
            warnings.warn("No image viewmodel to draw")

        self._draw_imageviewmodel(view_proj=view_proj,
                                  image_viewmodel=self._image_viewmodel,
                                  space=space)

    def _draw_imageviewmodel(self,
                             view_proj: NDArray[np.floating],
                             image_viewmodel: pyre.viewmodels.ImageViewModel | None,
                             space: pyre.Space,
                             bounding_box: nornir_imageregistration.Rectangle | None = None):

        if image_viewmodel is None:
            return

        tween = 0 if space == Space.Source else 1

        for ix in range(0, image_viewmodel.NumCols):
            column = image_viewmodel.ImageArray[ix]
            for iy in range(0, image_viewmodel.NumRows):
                texture = column[iy]

                render_data = self.get_or_create_tile_globjects(ix, iy)

                shaders.texture_shader.draw(view_proj, texture, render_data.vao, tween=tween)
