"""
Created on Oct 19, 2012

@author: u0490822
"""

# from imageop import scale
from abc import ABC, abstractmethod
import logging
import math
import time
from numpy.typing import NDArray
import scipy.spatial
import scipy.spatial.distance
import numpy as np
from typing import Any

import nornir_imageregistration
import nornir_imageregistration.transforms.base
import nornir_imageregistration.transforms.triangulation

import OpenGL.GL as gl
from OpenGL.arrays import vbo
import pyre
import pyre.gl_engine.shaders as shaders
from pyre.gl_engine.texture_vertex_buffer import ShaderVAO


class RenderCache(object):
    """This object stores variables that must be calculated every time the transform changes"""
    PointCache: Any = None
    FixedImageDataGrid: None | list[list[int]]
    WarpedImageDataGrid: None | list[list[int]]
    LastSelectedPointIndex: int | None = None

    def __del__(self):
        self.PointCache = None
        self.FixedImageDataGrid = None
        self.WarpedImageDataGrid = None
        self.LastSelectedPointIndex = None


class PointTextures(object):
    """
    Provides graphics for transform points
    """

    __pointImage = None
    __selectedPointImage = None
    __pointGroup = None
    __selectedPointSpriteOn = None
    __selectedPointSpriteOff = None

    @property
    def PointImage(self):
        if PointTextures.__pointImage is None:
            PointTextures.LoadTextures()

        return PointTextures.__pointImage

    @property
    def SelectedPointImage(self):
        if PointTextures.__selectedPointImage is None:
            PointTextures.LoadTextures()

        return PointTextures.__selectedPointImage

    @property
    def PointGroup(self):
        if PointTextures.__pointGroup is None:
            PointTextures.LoadTextures()

        return PointTextures.__pointGroup

    @property
    def SelectedPointSpriteOn(self):
        if PointTextures.__selectedPointSpriteOn is None:
            PointTextures.LoadTextures()

        return PointTextures.__selectedPointSpriteOn

    @property
    def SelectedPointSpriteOff(self):
        if PointTextures.__selectedPointSpriteOff is None:
            PointTextures.LoadTextures()

        return PointTextures.__selectedPointSpriteOff

    @classmethod
    def LoadTextures(cls):
        return
        #
        # if cls.__pointImage is None:
        #     cls.__pointImage = pyglet.image.load(os.path.join(pyre.resources.ResourcePath(), "Point.png"))
        #     cls.__pointImage.anchor_x = cls.__pointImage.width // 2
        #     cls.__pointImage.anchor_y = cls.__pointImage.height // 2
        #
        # if cls.__selectedPointImage is None:
        #     cls.__selectedPointImage = pyglet.image.load(
        #         os.path.join(pyre.resources.ResourcePath(), "SelectedPoint.png"))
        #     cls.__selectedPointImage.anchor_x = cls.__selectedPointImage.width // 2
        #     cls.__selectedPointImage.anchor_y = cls.__selectedPointImage.height // 2
        #
        # if cls.__pointGroup is None:
        #     cls.__pointGroup = pyglet.sprite.SpriteGroup(texture=cls.__pointImage.get_texture(),
        #                                                  blend_src=pyglet.gl.GL_SRC_ALPHA,
        #                                                  blend_dest=pyglet.gl.GL_ONE_MINUS_SRC_ALPHA,
        #                                                  program=pyglet.sprite.get_default_shader())
        #     cls.__selectedPointSpriteOn = pyglet.sprite.Sprite(cls.__selectedPointImage, 0, 0, group=cls.__pointGroup)
        #     cls.__selectedPointSpriteOff = pyglet.sprite.Sprite(cls.__pointImage, 0, 0, group=cls.__pointGroup)


class ImageTransformViewBase(ABC):
    """
    Base class for ImageTransformView objects
    """

    @property
    @abstractmethod
    def width(self) -> int:
        """Width of the image in pixels"""
        raise NotImplementedError()

    @property
    @abstractmethod
    def height(self) -> int:
        """Height of the image in pixels"""
        raise NotImplementedError()

    @property
    @abstractmethod
    def Transform(self) -> nornir_imageregistration.ITransform:
        """Transform applied to the image to move it from source to target space"""
        raise NotImplementedError()

    @abstractmethod
    def draw_textures(self,
                      view_proj: NDArray[np.floating],
                      ShowWarped: bool = True,
                      BoundingBox: nornir_imageregistration.Rectangle | None = None,
                      glFunc=None):
        """Draw the image in either source (fixed) or target (warped) space
        :param view_proj: View projection matrix"""
        raise NotImplementedError()


class ImageGridTransformView(ImageTransformViewBase, PointTextures):
    """
    Combines and image and a transform to render an image.  Read-only operations used for rendering the graphics.
    """

    _z: float
    _ImageViewModel: pyre.viewmodels.ImageViewModel
    _TransformController: pyre.viewmodels.TransformController
    Debug: bool
    _index_buffer: vbo.VBO
    _vertex_buffer: vbo.VBO
    rendercache: RenderCache

    @property
    def width(self) -> int:
        if self._ImageViewModel is None:
            return 1

        return self._ImageViewModel.width

    @property
    def height(self) -> int:
        if self._ImageViewModel is None:
            return 1

        return self._ImageViewModel.height

    @property
    def ImageViewModel(self) -> pyre.viewmodels.ImageViewModel:
        return self._ImageViewModel

    @property
    def ImageMaskViewModel(self) -> pyre.viewmodels.ImageViewModel | None:
        return self._ImageMaskViewModel

    @property
    def Transform(self) -> nornir_imageregistration.ITransform:
        return self._TransformController.TransformModel

    @property
    def TransformController(self) -> pyre.viewmodels.TransformController:
        return self._TransformController

    @TransformController.setter
    def TransformController(self, value: pyre.viewmodels.TransformController):
        if self._TransformController is not None:
            self._TransformController.RemoveOnChangeEventListener(self.OnTransformChanged)

        self._TransformController = value

        if value is not None:
            if not isinstance(value, pyre.viewmodels.TransformController):
                raise ValueError(f"Expected TransformController type, got {value}")
            self._TransformController.AddOnChangeEventListener(self.OnTransformChanged)

        self.OnTransformChanged()

    @property
    def z(self) -> float:
        return self._z

    @z.setter
    def z(self, value: float):
        self._z = value

    def __init__(self, ImageViewModel: pyre.viewmodels.ImageViewModel,
                 ImageMaskViewModel: pyre.viewmodels.ImageViewModel | None = None,
                 Transform: pyre.viewmodels.TransformController | None = None):
        """
        Constructor
        :param imageviewmodel ImageViewModel: Textures for image
        :param transform Transform: nornir_imageregistration transform
        """
        self._TransformController = None

        self.rendercache = RenderCache()
        self._ImageViewModel = ImageViewModel
        self._ImageMaskViewModel = ImageMaskViewModel
        self.TransformController = Transform
        self._z = 0.5
        self._buffers = None

        self.Debug = False

    def OnTransformChanged(self):

        self._buffers = None
        if not isinstance(self.Transform, nornir_imageregistration.transforms.IControlPoints):
            SavedPointCache = None
        else:
            # Keep the points if we can
            SavedPointCache = RenderCache()
            if hasattr(self.rendercache, 'PointCache'):
                PointCache = self.rendercache.PointCache
                if hasattr(PointCache, 'Sprites'):
                    if len(PointCache.Sprites) == len(self.Transform.TargetPoints):
                        SavedPointCache = PointCache

        self.rendercache = None
        self.rendercache = RenderCache()

        if SavedPointCache is not None:
            self.rendercache.PointCache = SavedPointCache

    @classmethod
    def get_sprite_position(cls, sprites):
        if sprites is None:
            return None

        return np.asarray(list(map(lambda s: np.asarray((s.y, s.x)), sprites)))

    @property
    def sprite_position(self):
        if not hasattr(self.PointCache, 'Sprites'):
            return None

        return ImageGridTransformView.get_sprite_position(self.PointCache.sprites)

    @classmethod
    def _batch_update_sprite_position(cls, sprites, points: NDArray[np.floating], scales):

        iChanged = ImageGridTransformView.get_sprite_position(sprites) != points
        iChanged = np.max(iChanged, 1)

        ChangedSprites = [s for i, s in enumerate(sprites) if iChanged[i]]
        ChangedPoints = points[iChanged]

        for i, s in enumerate(ChangedSprites):
            s.set_position(ChangedPoints[nornir_imageregistration.iPoint.X],
                           ChangedPoints[nornir_imageregistration.iPoint.Y])

        iChangedScale = list(map(lambda s: s.scale, sprites)) != scales
        ChangedSprites = [s for i, s in enumerate(sprites) if iChanged[i]]

        if isinstance(scales, np.ndarray) or isinstance(scales, list):
            ChangedScales = scales[iChangedScale]
        else:
            ChangedScales = scales

        for i, s in enumerate(ChangedSprites):
            s.scale = ChangedScales[i]

    @classmethod
    def _update_sprite_position(cls, sprite, point: NDArray[np.floating], scale: float):
        if sprite.x != point[nornir_imageregistration.iPoint.X] or sprite.y != point[nornir_imageregistration.iPoint.Y]:
            sprite.set_position(point[nornir_imageregistration.iPoint.X], point[nornir_imageregistration.iPoint.Y])

        if sprite.scale != scale:
            sprite.scale = scale

    def _update_sprite_flash(self, sprite, is_selected: bool, time_for_selected_to_flash: bool = False):

        if not is_selected:
            if sprite.image.id != self.PointImage._current_texture.id:
                #                if sprite.image != self.PointImage:
                sprite.image = self.PointImage
                return

        else:
            if time_for_selected_to_flash:
                sprite.image = self.SelectedPointImage
            else:
                sprite.image = self.PointImage

    def _draw_points(self,
                     verts,
                     SelectedIndex: int | None = None,
                     BoundingBox: nornir_imageregistration.Rectangle | None = None,
                     ScaleFactor: float = 1.0):

        PointBaseScale = 8.0

        current_time = time.time()
        time_for_selected_to_flash = current_time % 1 > 0.5
        # print('%g = %d' % (current_time % 1, time_for_selected_to_flash))

        PointCache = RenderCache()
        if hasattr(self.rendercache, 'PointCache'):
            if not self.rendercache.PointCache is None:
                PointCache = self.rendercache.PointCache

        #         self.PointImage.anchor_x = self.PointImage.width // 2
        #         self.PointImage.anchor_y = self.PointImage.height // 2
        #
        #         self.SelectedPointImage.anchor_x = self.PointImage.width // 2
        #         self.SelectedPointImage.anchor_y = self.PointImage.height // 2

        scale = (PointBaseScale / float(self.PointImage.width)) * float(ScaleFactor)

        if scale < PointBaseScale / float(self.PointImage.width):
            scale = PointBaseScale / float(self.PointImage.width)

        if hasattr(PointCache, 'LastSelectedPointIndex'):
            if self.rendercache.LastSelectedPointIndex != SelectedIndex:
                if hasattr(PointCache, 'sprites'):
                    del PointCache.sprites
                    del PointCache.PointBatch

        self.rendercache.LastSelectedPointIndex = SelectedIndex

        if hasattr(PointCache, 'Sprites'):
            try:
                sprites = PointCache.Sprites
                PointBatch = PointCache.PointBatch

                ImageGridTransformView._batch_update_sprite_position(sprites, verts, scale)

                for i, s in enumerate(sprites):
                    # ImageGridTransformView._update_sprite_position(sprites[i], verts[i], scale)
                    is_selected = i == SelectedIndex
                    self._update_sprite_flash(s, is_selected, time_for_selected_to_flash)

                gl.glDisable(gl.GL_DEPTH_TEST)
                PointBatch.draw()
                gl.glEnable(gl.GL_DEPTH_TEST)
            except:
                self.rendercache.PointCache = None
                l = logging.getLogger('ImageGridTransformView')
                l.error("Cached Point sprite error, resetting cache")

        else:
            PointBatch = pyglet.graphics.Batch()
            spriteList = list()
            for i in range(0, len(verts)):
                point = verts[i]

                # if math.isnan(point[0]) or math.isnan(point[1]):
                #    continue

                Image = self.PointImage
                if math.isnan(point[0]) or math.isnan(point[1]):
                    continue

                if SelectedIndex is not None:
                    if i == SelectedIndex and time_for_selected_to_flash:
                        Image = self.SelectedPointImage

                s = pyglet.sprite.Sprite(Image, x=point[1], y=point[0], group=self.PointGroup, batch=PointBatch)
                s.scale = scale
                spriteList.append(s)

            PointCache.Sprites = spriteList
            PointCache.PointBatch = PointBatch

            gl.glDisable(gl.GL_DEPTH_TEST)
            PointBatch.draw()
            gl.glEnable(gl.GL_DEPTH_TEST)

            self.rendercache.PointCache = PointCache
            # print str(s.x) + ", " + str(s.y)

        # PointBatch.draw()

    def draw_points(self, SelectedIndex: int | None = None,
                    FixedSpace: bool = True,
                    BoundingBox: nornir_imageregistration.Rectangle | None = None,
                    ScaleFactor: float = 1.0):

        if isinstance(self.Transform, nornir_imageregistration.IControlPoints):
            if not FixedSpace:
                verts = self.Transform.SourcePoints
            else:
                verts = self.Transform.TargetPoints

            self._draw_points(verts, SelectedIndex, BoundingBox, ScaleFactor)

    def draw_lines(self, draw_in_fixed_space: bool):
        """
        :param bool draw_in_fixed_space: True if lines should be drawn in fixed space.  Otherwise draw in warped space
        """
        if self.Transform is None:
            return

        Triangles = []
        if not draw_in_fixed_space:
            if not isinstance(self.Transform, nornir_imageregistration.transforms.ITriangulatedSourceSpace):
                return

            # Triangles = self.__Transform.WarpedTriangles
            verts = np.fliplr(self.Transform.SourcePoints)
            Triangles = self.Transform.source_space_trianglulation
        else:
            if not isinstance(self.Transform, nornir_imageregistration.transforms.ITriangulatedTargetSpace):
                return

            verts = np.fliplr(self.Transform.TargetPoints)
            Triangles = self.Transform.target_space_trianglulation

        if verts is not None and Triangles is not None:
            pyre.views.DrawTriangles(verts, Triangles)

    @classmethod
    def _fixed_texture_coords(cls):
        t = (0.0, 0.0, 0,
             1.0, 0.0, 0,
             1.0, 1.0, 0,
             0.0, 1.0, 0,
             0.5, 0.5, 1.0)

    def DrawFixedImage(self,
                       view_proj: NDArray[np.floating],
                       image_view_model: ImageViewModel,
                       color: tuple[float, float, float, float] | None = None,
                       BoundingBox: nornir_imageregistration.RectLike | None = None,
                       z: float | int = None):
        """Draw a fixed image, bounding box indicates the visible area.  Everything is drawn if BoundingBox is None"""

        if z is None:
            z = self.z

        if hasattr(self.rendercache, 'FixedImageDataGrid'):
            FixedImageDataGrid = self.rendercache.FixedImageDataGrid
        else:
            FixedImageDataGrid = []
            for i in range(0, image_view_model.NumCols):
                FixedImageDataGrid.append([None] * image_view_model.NumRows)
                self.rendercache.FixedImageDataGrid = FixedImageDataGrid

        if color is None:
            color = (1.0, 1.0, 1.0, 1.0)

        gl.glEnable(gl.GL_TEXTURE_2D)
        gl.glDisable(gl.GL_CULL_FACE)

        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_S, gl.GL_CLAMP_TO_BORDER)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_T, gl.GL_CLAMP_TO_BORDER)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_NEAREST)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_NEAREST)

        gl.glBlendColor(color[0], color[1], color[2], color[3])

        for ix in range(0, image_view_model.NumCols):
            column = image_view_model.ImageArray[ix]
            cacheColumn = FixedImageDataGrid[ix]
            for iy in range(0, image_view_model.NumRows):

                texture = column[iy]
                t = (0.0, 0.0, z,
                     1.0, 0.0, z,
                     1.0, 1.0, z,
                     0.0, 1.0, z)
                h, w = image_view_model.TextureSize
                x = image_view_model.TextureSize[1] * ix
                y = image_view_model.TextureSize[0] * iy

                # Check bounding box if it exists
                if BoundingBox is not None:
                    if not nornir_imageregistration.spatial.Rectangle.contains(BoundingBox, [y, x, y + h, x + w]):
                        continue

                array = None
                if cacheColumn[iy] is None:
                    array = (gl.GLfloat * 32)(
                        t[0], t[1],
                        x, y, z,
                        t[3], t[4],
                        x + w, y, z,
                        t[6], t[7],
                        x + w, y + h, z,
                        t[9], t[10],
                        x, y + h, z)

                    cacheColumn[iy] = array
                else:
                    array = cacheColumn[iy]

                gl.glActiveTexture(gl.GL_TEXTURE0)
                gl.glBindTexture(gl.GL_TEXTURE_2D, texture)
                try:
                    gl.glEnableClientState(gl.GL_VERTEX_ARRAY)
                    gl.glPushClientAttrib(gl.GL_CLIENT_VERTEX_ARRAY_BIT)
                    gl.glInterleavedArrays(gl.GL_T2F_V3F, 0, array)
                    gl.glDrawArrays(gl.GL_QUADS, 0, 4)
                finally:
                    gl.glDisableClientState(gl.GL_VERTEX_ARRAY);

        # gl.glColor4f(1.0, 1.0, 1.0, 1.0)

    def GetOrCreateWarpedImageDataGrid(self, grid_size: tuple[int, int]) -> list[list[None]]:
        """
        Grab the cached image data for a warped image
        """

        WarpedImageDataGrid = None
        if hasattr(self.rendercache, 'WarpedImageDataGrid'):
            WarpedImageDataGrid = self.rendercache.WarpedImageDataGrid
        else:
            WarpedImageDataGrid = []
            for i in range(0, grid_size[1]):
                WarpedImageDataGrid.append([None] * grid_size[0])

            self.rendercache.WarpedImageDataGrid = WarpedImageDataGrid

        return WarpedImageDataGrid

    @classmethod
    def _tile_grid_points(cls, tile_bounding_rect: nornir_imageregistration.Rectangle,
                          grid_size: tuple[int, int] = (8, 8)):
        """
        :return: Fills the tile area with a (MxN) grid of points.  Maps the points through the transform.  Then adds the known transform points to the results
        """

        (y, x) = tile_bounding_rect.BottomLeft
        h = int(tile_bounding_rect.Height)
        w = int(tile_bounding_rect.Width)

        WarpedCornersO = [[y, x],
                          [y, x + w, ],
                          [y + h, x],
                          [y + h, x + w]]

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

    @classmethod
    def _find_corresponding_points(self, Transform: nornir_imageregistration.ITransform,
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

        return np.hstack((FixedPoints, WarpedPoints))

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
        Extracts control points from a transform, merges them with the input points, and returns the result
        :param PointsA:
        :param TransformPoints:
        :return:
        """

        # This is a mess.  Transforms use the terminology Fixed & Warped to describe themselves.  The Transform function moves the warped points into fixed space.
        PointsB = np.hstack((TransformPoints[:, 2:4], TransformPoints[:, 0:2]))
        if len(PointsA) > 0 and len(PointsB) > 0:
            AllPointPairs = np.vstack([PointsA, PointsB])
            return AllPointPairs

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
        Z = np.power(centered_points, 2).sum(axis=1)
        Z = np.sqrt(Z)
        return Z

    @classmethod
    def _texture_coordinates(cls, FixedPointsYX: NDArray[np.floating],
                             fixed_bounding_rect: nornir_imageregistration.Rectangle) -> NDArray[np.floating]:
        """
        :param FixedPointsYX:
        :param fixed_bounding_rect:
        :return: texture coordinates for a rectangle in fixed (source) space
        """

        # tile_bounding_rect = nornir_imageregistration.spatial.BoundingPrimitiveFromPoints(SourcePoints)
        (y, x) = fixed_bounding_rect.BottomLeft
        h = fixed_bounding_rect.Height
        w = fixed_bounding_rect.Width

        texturePoints = (FixedPointsYX - np.array(fixed_bounding_rect.BottomLeft)) / fixed_bounding_rect.Size

        # Need to convert to X,Y coordinates
        texturePoints = np.fliplr(texturePoints)
        return texturePoints

    @classmethod
    def _render_data_for_transform_point_pairs(cls,
                                               PointPairs: NDArray[np.floating],
                                               tile_bounding_rect: nornir_imageregistration.Rectangle,
                                               z: float | None = None) -> tuple[vbo.VBO, vbo.VBO, vbo.VBO]:
        """
        Generate verticies (source, target and texture coordinates) for a set of transform points and the
        indicies to render them as triangles
        :return: Verts3D, indicies, Verts3d is Source (X,Y,Z), Target (X,Y,Z), Texture (U,V)
        """

        FixedPointsYX, WarpedPointsYX = np.hsplit(PointPairs, 2)

        # tile_bounding_rect = nornir_imageregistration.spatial.BoundingPrimitiveFromPoints(SourcePoints)
        # Need to convert from Y,x to X,Y coordinates
        # FixedPointsXY = np.fliplr(FixedPointsYX)
        WarpedPointsXY = np.fliplr(WarpedPointsYX)
        # Do triangulation before we transform the points to prevent concave edges having a texture mapped over them.

        # texturePoints = (FixedPointsXY - np.array((x,y))) / np.array((w,h))

        texturePoints = cls._texture_coordinates(FixedPointsYX, fixed_bounding_rect=tile_bounding_rect)
        # print(str(texturePoints[0, :]))
        tri = scipy.spatial.Delaunay(texturePoints)
        # np.array([[(u - x) / float(w), (v - y) / float(h)] for u, v in FixedPointsXY], dtype=np.float32)

        # Set vertex z according to distance from center
        if z is not None:
            z_array = np.ones((FixedPointsYX.shape[0], 1)) * z
        else:
            z_array = cls._z_values_for_points_by_texture(texturePoints)

        Verts3D = np.vstack((FixedPointsYX[:, 1],
                             FixedPointsYX[:, 0],
                             z_array.flat,
                             WarpedPointsXY[:, 1],
                             WarpedPointsXY[:, 0],
                             z_array.flat,
                             texturePoints[:, 0],
                             texturePoints[:, 1])).T

        Verts3D = Verts3D.astype(np.float32)

        indicies = tri.simplices.flatten().astype(np.uint16)

        return Verts3D, indicies

    def DrawWarpedImage(self,
                        view_proj: NDArray[np.floating],
                        image_view_model: pyre.viewmodels.ImageViewModel,
                        ForwardTransform: bool = True,
                        tex_color=None,
                        BoundingBox: nornir_imageregistration.Rectangle | None = None,
                        z: float | None = None,
                        glFunc: int = gl.GL_FUNC_ADD,
                        tween: float = 1.0):

        if image_view_model.NumCols > 1 or image_view_model.NumRows > 1:
            return self._draw_warped_imagegridviewmodel(view_proj, image_view_model, ForwardTransform=True,
                                                        tex_color=tex_color,
                                                        BoundingBox=BoundingBox, z=z, tween=tween, glFunc=glFunc)

        # The rest of this is the case for a texture so small it did not need to be subdivided

        warped_image_data_grid = self.GetOrCreateWarpedImageDataGrid(
            (image_view_model.NumRows, image_view_model.NumCols))

        if warped_image_data_grid[0][0] is None:
            tile_fixed_bounding_rect = nornir_imageregistration.spatial.Rectangle.CreateFromPointAndArea((0, 0),
                                                                                                         image_view_model.TextureSize)

            AllPointPairs = ImageGridTransformView._build_tile_point_pairs(self.Transform, tile_fixed_bounding_rect,
                                                                           ForwardTransform=ForwardTransform)
            (vertarray, indicies) = ImageGridTransformView._render_data_for_transform_point_pairs(
                AllPointPairs,
                tile_fixed_bounding_rect,
                None)
            vertex_array_object = ShaderVAO(pyre.shaders.TextureShader, vertarray, indicies)
            warped_image_data_grid[0][0] = vertex_array_object
        else:
            vertex_array_object = warped_image_data_grid[0][0]

        texture = image_view_model.ImageArray[0][0]

        # if self._vertex_buffer is None:
        #     self._vertex_buffer = pyre.views.GetOrCreateVertexBuffer(vertarray)
        # if self._buffers is None:
        #     self._buffers = pyre.views.GetOrCreateBuffers(len(vertarray) / 3,
        #                                                   ('v3f', vertarray),
        #                                                   ('t2f', texarray))

        pyre.shaders.TextureShader.draw(view_proj, texture, vertex_buffer, index_buffer, tween=1)
        # pyre.gl_engine.shaders.ColorShader.draw(view_proj, vertex_array_object)
        # pyre.views.DrawTextureWithBuffers(texture, vertex_buffer, index_buffer, tex_color,
        #                                   glFunc=glFunc)
        return

    def _draw_warped_imagegridviewmodel(self,
                                        view_proj: NDArray[np.floating],
                                        image_view_model: pyre.viewmodels.ImageViewModel,
                                        ForwardTransform: bool = True,
                                        tex_color=None,
                                        BoundingBox: nornir_imageregistration.Rectangle | None = None,
                                        z: float | None = None,
                                        tween: float = 1.0,
                                        glFunc: int = gl.GL_FUNC_ADD):

        if z is None:
            z = self.z

        if tex_color is None:
            tex_color = (1.0, 1.0, 1.0, 1.0)

        warped_image_data_grid = self.GetOrCreateWarpedImageDataGrid(
            (image_view_model.NumRows, image_view_model.NumCols))

        for ix in range(0, image_view_model.NumCols):
            column = image_view_model.ImageArray[ix]
            for iy in range(0, image_view_model.NumRows):
                texture = column[iy]
                x = image_view_model.TextureSize[1] * ix
                y = image_view_model.TextureSize[0] * iy

                vertarray = None
                texarray = None
                verts = None
                tilecolor = None

                if warped_image_data_grid[ix][iy] is None:

                    tile_fixed_bounding_rect = nornir_imageregistration.spatial.Rectangle.CreateFromPointAndArea((y, x),
                                                                                                                 image_view_model.TextureSize)

                    AllPointPairs = ImageGridTransformView.collect_vertex_locations_within_bounding_box_after_transformation(
                        bounding_box=tile_fixed_bounding_rect,
                        transform=self.Transform,
                        ForwardTransform=ForwardTransform)

                    vertarray, indicies = ImageGridTransformView._render_data_for_transform_point_pairs(
                        AllPointPairs, tile_fixed_bounding_rect, z=None)

                    # vertarray = vbo.VBO(vertarray, target=gl.GL_ARRAY_BUFFER)
                    # indicies = vbo.VBO(indicies, target=gl.GL_ELEMENT_ARRAY_BUFFER)

                    # warped_image_data_grid[ix][iy] = (vertarray, indicies)
                    vertex_array_object = ShaderVAO(shaders.texture_shader, vertarray, indicies)
                    if vertex_array_object.num_elements == 0:
                        raise ValueError("No elements in vertex array object")
                    warped_image_data_grid[ix][iy] = vertex_array_object
                else:
                    vertex_array_object = warped_image_data_grid[ix][iy]

                shaders.texture_shader.draw(view_proj, texture, vertex_array_object, tween=tween)
                # shaders.color_shader.draw(view_proj, vertex_array_object, tween=tween)
                # pyre.views.DrawTexture(texture, vertarray, indicies, tex_color, glFunc=glFunc)

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
        GridPoints = ImageGridTransformView._tile_grid_points(bounding_box, grid_size=(8, 8))
        GridPointPairs = ImageGridTransformView._find_corresponding_points(transform, GridPoints,
                                                                           ForwardTransform=ForwardTransform)

        if isinstance(transform, nornir_imageregistration.IControlPoints):
            TransformPoints = transform.GetPointPairsInSourceRect(
                bounding_box) if ForwardTransform else transform.GetPointPairsInTargetRect(bounding_box)

            AllPointPairs = GridPointPairs if TransformPoints is None else ImageGridTransformView._merge_point_pairs_with_transform(
                GridPointPairs,
                TransformPoints)
        else:
            return GridPointPairs

        return AllPointPairs

    def CreateLabelVertexNumberBatch(self, verts: NDArray[np.floating]):
        LabelBatch = pyglet.graphics.Batch()

        for i in range(0, verts.shape[0]):
            p = verts[i]
        #         l = pyglet.text.Label(text = str(i), font_name = 'Times New Roman', font_size = 36, x = p[0], y = p[1], color = (255, 255, 255, 255), width = 128, height = 128, anchor_x = 'center', anchor_y = 'center', batch = LabelBatch)

        return LabelBatch

    def draw_textures(self, view_proj: NDArray[np.floating],
                      ShowWarped: bool = True,
                      BoundingBox: nornir_imageregistration.Rectangle | None = None,
                      z: float | None = None,
                      glFunc: int | None = None):
        if self.ImageViewModel is None:
            return

        if ShowWarped:
            self.DrawWarpedImage(view_proj, self.ImageViewModel, tex_color=None, BoundingBox=BoundingBox, z=z, tween=0)
        else:
            self.DrawWarpedImage(view_proj, self.ImageViewModel, tex_color=None, BoundingBox=BoundingBox, z=z, tween=1)
