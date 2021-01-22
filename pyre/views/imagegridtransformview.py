
'''
Created on Oct 19, 2012

@author: u0490822
'''

#from imageop import scale
import logging
import math
import os
import time

import nornir_imageregistration.spatial
import nornir_imageregistration.transforms.base
import nornir_imageregistration.transforms.triangulation
import numpy
import pyglet
import scipy.spatial
import scipy.spatial.distance

import pyglet.gl as gl
import pyre


class RenderCache(object):
    '''This object stores variables that must be calculated every time the transform changes'''
        
    pass


class PointTextures(object):
    '''
    Provides graphics for transform points
    '''
    
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
        if cls.__pointImage is None:
            cls.__pointImage = pyglet.image.load(os.path.join(pyre.resources.ResourcePath(), "Point.png"))
            cls.__pointImage.anchor_x = cls.__pointImage.width // 2
            cls.__pointImage.anchor_y = cls.__pointImage.height // 2
            
        if cls.__selectedPointImage is None:
            cls.__selectedPointImage = pyglet.image.load(os.path.join(pyre.resources.ResourcePath(), "SelectedPoint.png"));
            cls.__selectedPointImage.anchor_x = cls.__selectedPointImage.width // 2
            cls.__selectedPointImage.anchor_y = cls.__selectedPointImage.height // 2
 
        if cls.__pointGroup is None:
            cls.__pointGroup = pyglet.sprite.SpriteGroup(texture=cls.__pointImage.get_texture(), blend_src=pyglet.gl.GL_SRC_ALPHA, blend_dest=pyglet.gl.GL_ONE_MINUS_SRC_ALPHA)
            cls.__selectedPointSpriteOn = pyglet.sprite.Sprite(cls.__selectedPointImage, 0, 0)
            cls.__selectedPointSpriteOff = pyglet.sprite.Sprite(cls.__pointImage, 0, 0)
    

class ImageTransformViewBase(object):
    '''
    Base class for ImageTransformView objects
    '''
      
    @property
    def width(self):
        raise NotImplementedError()

    @property
    def height(self):
        raise NotImplementedError()
    
    @property
    def Transform(self):
        raise NotImplementedError()
    
    def draw_textures(self, ShowWarped=True, BoundingBox=None, glFunc=None):
        raise NotImplementedError()
    

class ImageGridTransformView(ImageTransformViewBase, PointTextures):
    '''
    Combines and image and a transform to render an image.  Read-only operations used for rendering the graphics.
    '''
     
    @property
    def width(self):
        if self._ImageViewModel is None:
            return 1

        return self._ImageViewModel.width

    @property
    def height(self):
        if self._ImageViewModel is None:
            return 1

        return self._ImageViewModel.height

    @property
    def ImageViewModel(self):
        return self._ImageViewModel
    
    @property
    def ImageMaskViewModel(self):
        return self._ImageMaskViewModel;

    @property
    def Transform(self):
        return self._Transform

    @Transform.setter
    def Transform(self, value):
        if not self._Transform is None:
            self._Transform.RemoveOnChangeEventListener(self.OnTransformChanged)

        self._Transform = value

        if not value is None:
            assert(isinstance(value, nornir_imageregistration.transforms.base.Base))
            self._Transform.AddOnChangeEventListener(self.OnTransformChanged)
            
        self.OnTransformChanged()
 
    @property
    def z(self):
        return self._z
    
    @z.setter
    def z(self, value):
        self._z = value 

    def __init__(self, ImageViewModel, ImageMaskViewModel = None, Transform=None):
        '''
        Constructor
        :param imageviewmodel ImageViewModel: Textures for image
        :param transform Transform: nornir_imageregistration transform 
        '''
        self._Transform = None

        self.rendercache = RenderCache()
        self._ImageViewModel = ImageViewModel
        self._ImageMaskViewModel = ImageMaskViewModel
        self.Transform = Transform
        self._z = 0.5
        self._buffers = None

        self.Debug = False

    def OnTransformChanged(self):

        self._buffers = None
        # Keep the points if we can
        SavedPointCache = RenderCache()
        if hasattr(self.rendercache, 'PointCache'):
            PointCache = self.rendercache.PointCache
            if hasattr(PointCache, 'Sprites'):
                if len(PointCache.Sprites) == len(self.Transform.TargetPoints):
                    SavedPointCache = PointCache

        self.rendercache = None
        self.rendercache = RenderCache()

        if not SavedPointCache is None:
            self.rendercache.PointCache = SavedPointCache
            
    @classmethod
    def get_sprite_position(cls, sprites):
        if sprites is None:
            return None
        
        return numpy.asarray(list(map(lambda s: numpy.asarray((s.y, s.x)), sprites)))
            
    @property
    def sprite_position(self):
        if not hasattr(self.PointCache, 'Sprites'):
            return None
        
        return ImageGridTransformView.get_sprite_position(self.PointCache.sprites)

    @classmethod 
    def _batch_update_sprite_position(cls, sprites, points, scales):
        
        iChanged = ImageGridTransformView.get_sprite_position(sprites) != points
        iChanged = numpy.max(iChanged, 1)
        
        ChangedSprites = [s for i, s in enumerate(sprites) if iChanged[i]]
        ChangedPoints = points[iChanged]
        
        for i,s in enumerate(ChangedSprites):
            s.set_position(ChangedPoints[nornir_imageregistration.iPoint.X], point[nornir_imageregistration.iPoint.Y])

        iChangedScale = list(map(lambda s: s.scale, sprites)) != scales
        ChangedSprites = [s for i, s in enumerate(sprites) if iChanged[i]]
        
        if isinstance(scales, numpy.ndarray) or isinstance(scales, list):
            ChangedScales = scales[iChangedScale]
        else:  
            ChangedScales = scales
           
        for i,s in enumerate(ChangedSprites):
            s.scale = ChangedScales[i]
        
    
    @classmethod
    def _update_sprite_position(cls, sprite, point, scale):
        if sprite.x != point[nornir_imageregistration.iPoint.X] or sprite.y != point[nornir_imageregistration.iPoint.Y]:
            sprite.set_position(point[nornir_imageregistration.iPoint.X], point[nornir_imageregistration.iPoint.Y]) 
        
        if sprite.scale != scale:
            sprite.scale = scale
    
    def _update_sprite_flash(self, sprite, is_selected, time_for_selected_to_flash=False):
        
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

    def _draw_points(self, verts, SelectedIndex=None, BoundingBox=None, ScaleFactor=1.0):

        PointBaseScale = 8.0
        
        current_time = time.time()
        time_for_selected_to_flash = current_time % 1 > 0.5
        #print('%g = %d' % (current_time % 1, time_for_selected_to_flash))

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

        if(scale < PointBaseScale / float(self.PointImage.width)):
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
                
                for i,s in enumerate(sprites):
                    #ImageGridTransformView._update_sprite_position(sprites[i], verts[i], scale)
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
                    if(i == SelectedIndex and time_for_selected_to_flash):
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

    def draw_points(self, SelectedIndex=None, FixedSpace=True, BoundingBox=None, ScaleFactor=1):

        if(not FixedSpace):
            verts = self.Transform.SourcePoints
        else:
            verts = self.Transform.TargetPoints

        self._draw_points(verts, SelectedIndex, BoundingBox, ScaleFactor)

    def draw_lines(self, draw_in_fixed_space):
        '''
        :param bool draw_in_fixed_space: True if lines should be drawn in fixed space.  Otherwise draw in warped space
        '''
        if(self.Transform is None):
            return

        Triangles = []
        if not draw_in_fixed_space:
            # Triangles = self.__Transform.WarpedTriangles
            verts = numpy.fliplr(self.Transform.SourcePoints)
            Triangles = self.Transform.WarpedTriangles
        else:
            verts = numpy.fliplr(self.Transform.TargetPoints)
            Triangles = self.Transform.FixedTriangles
            
        pyre.views.DrawTriangles(verts, Triangles)
        
    @classmethod 
    def _fixed_texture_coords(cls):
        t = (0.0, 0.0, 0,
             1.0, 0.0, 0,
             1.0, 1.0, 0,
             0.0, 1.0, 0,
             0.5, 0.5, 1.0)

    def DrawFixedImage(self, ImageViewModel, color, BoundingBox=None, z=None):
        '''Draw a fixed image, bounding box indicates the visible area.  Everything is drawn if BoundingBox is None'''
        
        if z is None:
            z = self.z
        
        if hasattr(self.rendercache, 'FixedImageDataGrid'):
            FixedImageDataGrid = self.rendercache.FixedImageDataGrid
        else:
            FixedImageDataGrid = []
            for i in range(0, ImageViewModel.NumCols):
                FixedImageDataGrid.append([None] * ImageViewModel.NumRows)
                self.rendercache.FixedImageDataGrid = FixedImageDataGrid

        if color is None:
            color = (1.0, 1.0, 1.0, 1.0)
        
        gl.glEnable(gl.GL_TEXTURE_2D)
        gl.glDisable(gl.GL_CULL_FACE)
        
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_S, gl.GL_CLAMP_TO_BORDER)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_T, gl.GL_CLAMP_TO_BORDER)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_NEAREST)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_NEAREST)

        pyglet.gl.glColor4f(color[0], color[1], color[2], color[3])

        for ix in range(0, ImageViewModel.NumCols):
            column = ImageViewModel.ImageArray[ix]
            cacheColumn = FixedImageDataGrid[ix]
            for iy in range(0, ImageViewModel.NumRows):

                texture = column[iy]
                t = (0.0, 0.0, z,
                     1.0, 0.0, z,
                     1.0, 1.0, z,
                     0.0, 1.0, z)
                h, w = ImageViewModel.TextureSize
                x = ImageViewModel.TextureSize[1] * ix
                y = ImageViewModel.TextureSize[0] * iy

                # Check bounding box if it exists
                if not BoundingBox is None:
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

                gl.glBindTexture(gl.GL_TEXTURE_2D, texture)
                try:
                    gl.glPushClientAttrib(gl.GL_CLIENT_VERTEX_ARRAY_BIT)
                    gl.glInterleavedArrays(gl.GL_T2F_V3F, 0, array)
                    gl.glDrawArrays(gl.GL_QUADS, 0, 4)
                finally:
                    gl.glPopClientAttrib()
        
        pyglet.gl.glColor4f(1.0, 1.0, 1.0, 1.0)
                 
    def WarpedImageDataGrid(self, grid_size):
        '''Grab the cached image data for a warped image
        ''' 
        
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
    def _tile_grid_points(cls, tile_bounding_rect, grid_size=(8, 8)):
        '''
        :return: Fills the tile area with a (MxN) grid of points.  Maps the points through the transform.  Then adds the known transform points to the results
        '''
         
        (y, x) = tile_bounding_rect.BottomLeft
        h = int(tile_bounding_rect.Height)
        w = int(tile_bounding_rect.Width)
     
        WarpedCornersO = [[y, x],
                        [ y, x + w, ],
                        [y + h, x],
                        [ y + h, x + w]]
        
        grid_size = (int(grid_size[0]), int(grid_size[1]))
        WarpedCorners = numpy.zeros(((grid_size[0]+1) * (grid_size[1]+1), 2), dtype=numpy.float32)
        
        xstep = int(w / grid_size[1])
        ystep = int(h / grid_size[0])
        
        for iX in range(0, grid_size[1]+1):
            for iY in range(0, grid_size[0]+1):
                WarpedCorners[(iX * (grid_size[0]+1)) + iY] = ( y + (iY * ystep), x + (iX * xstep))

        #for xtemp in range(0, w + 1, xstep):
            #for ytemp in range(0, h + 1, ystep):
                #WarpedCorners.append([ytemp + y, xtemp + x])
                
        #WarpedCorners = numpy.array(WarpedCorners, dtype=numpy.float32)
        
        return WarpedCorners
    
    @classmethod
    def _tile_bounding_points(cls, tile_bounding_rect, grid_size=(3, 3)):
        '''
        :return: Returns a set of point pairs mapping the boundaries of the image tile
        '''
         
        (y, x) = tile_bounding_rect.BottomLeft
        h = int(tile_bounding_rect.Height)
        w = int(tile_bounding_rect.Width)
     
        WarpedCorners = [[y, x],
                        [ y, x + w, ],
                        [y + h, x],
                        [ y + h, x + w]]
        
        xstep = w // grid_size[1]
        ystep = h // grid_size[0] 
                        
        for ytemp in range(0, h + 1, int(ystep)):
            WarpedCorners.append([ytemp + y, 0 + x])
            WarpedCorners.append([ytemp + y, w + x])
            
        for xtemp in range(1, w, int(xstep)):
            WarpedCorners.append([0 + y, xtemp + x])
            WarpedCorners.append([h + y, xtemp + x])
            
        WarpedCorners = numpy.array(WarpedCorners, dtype=numpy.float32)
        
        return WarpedCorners

    @classmethod        
    def _find_corresponding_points(self, Transform, Points, ForwardTransform):
        '''Map the points through the transform and return the results as a Nx4 array of matched fixed and warped points'''
        
        # Figure out where the corners of the texture belong 
        if(ForwardTransform):
            FixedPoints = Points
            WarpedPoints = Transform.Transform(Points)
        else:
            FixedCorners = Transform.InverseTransform(Points)
            WarpedPoints = Points
            
        return numpy.hstack((FixedPoints, WarpedPoints))
    
    @classmethod
    def _tile_bounding_rect(cls, Transform, tile_bounding_rect, ForwardTransform=True, grid_size=(3.0, 3.0)):
        '''
        :return: Returns a bounding rectangle built from points placed around the edge of the tile
        '''
        BorderPoints = cls._tile_bounding_points(tile_bounding_rect=tile_bounding_rect, grid_size=grid_size)
        BorderPointPairs = cls._find_corresponding_points(Transform, BorderPoints, ForwardTransform=ForwardTransform)
        return nornir_imageregistration.spatial.Rectangle.CreateFromBounds(nornir_imageregistration.spatial.BoundsArrayFromPoints(BorderPointPairs[:, 0:2]))
     
    @classmethod
    def _merge_point_pairs_with_transform(cls, PointsA, TransformPoints):

        # This is a mess.  Transforms use the terminology Fixed & Warped to describe themselves.  The Transform function moves the warped points into fixed space.
        PointsB = numpy.hstack((TransformPoints[:, 2:4], TransformPoints[:, 0:2]))
        if len(PointsA) > 0 and len(PointsB) > 0:
            AllPointPairs = numpy.vstack([PointsA, PointsB])
            return AllPointPairs
        
        if len(PointsA) > 0:
            return PointsA
        
        if len(PointsB) > 0:
            return PointsB
        
    @classmethod
    def _build_subtile_point_pairs(cls, Transform, z, rect, ForwardTransform=True,):
        '''Determine transform points for a subregion of the transform'''
               
        TilePoints = cls._tile_grid_points(rect)
        TilePointPairs = cls._find_corresponding_points(Transform, TilePoints, ForwardTransform=ForwardTransform)
        TransformPointPairs = numpy.concatenate(numpy.array(Transform.GetWarpedPointsInRect(rect.ToArray())), 2).squeeze()
        AllPointPairs = cls._merge_point_pairs(TilePointPairs, TransformPointPairs)
        
        return AllPointPairs
           
    @classmethod
    def _build_tile_point_pairs(cls, Transform, z, rect, ForwardTransform=True,):
        '''Determine transform points for the entire transform, adding points around the boundary'''
               
        BorderPoints = cls._tile_bounding_points(rect)
        BorderPointPairs = cls._find_corresponding_points(Transform, BorderPoints, ForwardTransform=ForwardTransform)
        AllPointPairs = cls._merge_point_pairs_with_transform(BorderPointPairs, Transform.points)
        return AllPointPairs
           
    @classmethod
    def _z_values_for_points(cls, PointsYX):
        center = numpy.mean(PointsYX, 0)
        Z = scipy.spatial.distance.cdist(numpy.resize(center, (1, 2)), PointsYX, 'euclidean')
        Z = numpy.transpose(Z)
        Z /= numpy.max(Z)
        Z = 1 - Z
        return Z
         
    @classmethod 
    def _texture_coordinates(cls, FixedPointsYX, fixed_bounding_rect): 
        
        # tile_bounding_rect = nornir_imageregistration.spatial.BoundingPrimitiveFromPoints(SourcePoints)
        (y, x) = fixed_bounding_rect.BottomLeft
        h = fixed_bounding_rect.Height
        w = fixed_bounding_rect.Width
         
        texturePoints = (FixedPointsYX - numpy.array(fixed_bounding_rect.BottomLeft)) / fixed_bounding_rect.Size
        
        # Need to convert to X,Y coordinates
        texturePoints = numpy.fliplr(texturePoints) 
        return texturePoints
    
    @classmethod
    def _render_data_for_transform_point_pairs(cls, PointPairs, tile_bounding_rect, z=None):
        '''Generate verticies and texture coordinates for a set of transform points'''
         
        FixedPointsYX, WarpedPointsYX = numpy.hsplit(PointPairs, 2)
        
        # tile_bounding_rect = nornir_imageregistration.spatial.BoundingPrimitiveFromPoints(SourcePoints)
        # Need to convert from Y,x to X,Y coordinates
        # FixedPointsXY = numpy.fliplr(FixedPointsYX)
        WarpedPointsXY = numpy.fliplr(WarpedPointsYX)
        # Do triangulation before we transform the points to prevent concave edges having a texture mapped over them.

        # texturePoints = (FixedPointsXY - numpy.array((x,y))) / numpy.array((w,h))
        
        texturePoints = cls._texture_coordinates(FixedPointsYX, fixed_bounding_rect=tile_bounding_rect)
        #print(str(texturePoints[0, :]))
        tri = scipy.spatial.Delaunay(texturePoints)
        # numpy.array([[(u - x) / float(w), (v - y) / float(h)] for u, v in FixedPointsXY], dtype=numpy.float32)

        # Set vertex z according to distance from center
        if not z is None: 
            z_array = numpy.ones((FixedPointsYX.shape[0], 1)) * z
        else:
            z_array = cls._z_values_for_points(FixedPointsYX)
        
        Verts3D = numpy.hstack((WarpedPointsXY, z_array))
        vertarray = list(Verts3D.flat)
        texarray = list(texturePoints.flat)
          
        vertarray = (gl.GLfloat * len(vertarray))(*vertarray)
        texarray = (gl.GLfloat * len(texarray))(*texarray)

        verts = tri.vertices 

        verts = verts.flatten()
        
        return (vertarray, texarray, verts)
    
    def DrawWarpedImage(self, ImageViewModel, ForwardTransform=True, tex_color=None, BoundingBox=None, z=None, glFunc=gl.GL_FUNC_ADD):
            
        if ImageViewModel.NumCols > 1 or ImageViewModel.NumRows > 1:
            return self._draw_warped_imagegridviewmodel(ImageViewModel, ForwardTransform=True, tex_color=tex_color, BoundingBox=BoundingBox, z=z, glFunc=glFunc)
        
        WarpedImageDataGrid = self.WarpedImageDataGrid((ImageViewModel.NumRows, ImageViewModel.NumCols))
        
        if WarpedImageDataGrid[0][0] is None:
            tile_fixed_bounding_rect = nornir_imageregistration.spatial.Rectangle.CreateFromPointAndArea((0, 0), ImageViewModel.TextureSize)
            
            AllPointPairs = ImageGridTransformView._build_tile_point_pairs(self.Transform, z, tile_fixed_bounding_rect, ForwardTransform=ForwardTransform)
            (vertarray, texarray, verts) = ImageGridTransformView._render_data_for_transform_point_pairs(AllPointPairs, tile_fixed_bounding_rect, z) 
            WarpedImageDataGrid[0][0] = (vertarray, texarray, verts)
        else:
            (vertarray, texarray, verts) = WarpedImageDataGrid[0][0]
        
        texture = ImageViewModel.ImageArray[0][0]
        
        if self._buffers is None:
            self._buffers = pyre.views.GetOrCreateBuffers(len(vertarray) / 3,
                                                  ('v3f', vertarray),
                                                  ('t2f', texarray)) 
        
        pyre.views.DrawTextureWithBuffers(texture, vertarray, self._buffers, verts, tex_color, glFunc=glFunc) 
        return 
        
    def _draw_warped_imagegridviewmodel(self, ImageViewModel, ForwardTransform=True, tex_color=None, BoundingBox=None, z=None, glFunc=gl.GL_FUNC_ADD):
        
        if z is None:
            z = self.z
            
        if tex_color is None:
            tex_color = (1.0, 1.0, 1.0, 1.0)
            
        WarpedImageDataGrid = self.WarpedImageDataGrid((ImageViewModel.NumRows, ImageViewModel.NumCols))
  
        for ix in range(0, ImageViewModel.NumCols):
            column = ImageViewModel.ImageArray[ix]
            for iy in range(0, ImageViewModel.NumRows):
                texture = column[iy]
                x = ImageViewModel.TextureSize[1] * ix
                y = ImageViewModel.TextureSize[0] * iy 

                tile_fixed_bounding_rect = nornir_imageregistration.spatial.Rectangle.CreateFromPointAndArea((y, x), ImageViewModel.TextureSize)

                vertarray = None
                texarray = None
                verts = None
                tilecolor = None

                if WarpedImageDataGrid[ix][iy] is None:
    
                    # warped_bounding_rect = ImageGridTransformView._tile_bounding_rect(self.Transform, tile_fixed_bounding_rect, ForwardTransform)
                    # if not nornir_imageregistration.spatial.Rectangle.contains(BoundingBox, warped_bounding_rect):
                    #    continue
    
                    GridPoints = ImageGridTransformView._tile_grid_points(tile_fixed_bounding_rect, grid_size=(8, 8))
                    GridPointPairs = ImageGridTransformView._find_corresponding_points(self.Transform, GridPoints, ForwardTransform=ForwardTransform)
                    TransformPoints = self.Transform.GetPointsInWarpedRect(tile_fixed_bounding_rect)
                    if TransformPoints is None:
                        AllPointPairs = GridPointPairs
                    else:
                        AllPointPairs = ImageGridTransformView._merge_point_pairs_with_transform(GridPointPairs, TransformPoints)
    
                    vertarray, texarray, verts = ImageGridTransformView._render_data_for_transform_point_pairs(AllPointPairs, tile_fixed_bounding_rect, z=z)
    
                    WarpedImageDataGrid[ix][iy] = (vertarray, texarray, verts)
                else:
                    vertarray, texarray, verts = WarpedImageDataGrid[ix][iy]

                pyre.views.DrawTexture(texture, vertarray, texarray, verts, tex_color, glFunc=glFunc)

#                 if self.Debug:
#                     tilecolor = numpy.random.rand(4).tolist()
#                     LabelBatch.draw()
# 
#                     LineIndicies = pyre.views.LineIndiciesFromTri(verts)
# 
#                     gl.glDisable(gl.GL_TEXTURE_2D)
#                     pyglet.gl.glColor3f(tilecolor[0], tilecolor[1], tilecolor[2])
#                     pyglet.graphics.draw_indexed(len(vertarray) / 3,
#                                                              gl.GL_LINES,
#                                                              LineIndicies,
#                                                              ('v3f', vertarray))
# 
#                     pyglet.gl.glColor4f(1.0, 1.0, 1.0, 1.0)
#                     NumTestPoints = 16
#                     p = numpy.zeros([NumTestPoints, 2])
#                     p[:, 1] = [512] * NumTestPoints
#                     p[:, 0] = range(0, 1024, 1024 / NumTestPoints)
#                     tp = self.Transform.ForwardRBFInstance.Transform(p)
# 
#                     self._draw_points(tp)
# 
#                     p = numpy.zeros([NumTestPoints, 2])
#                     p[:, 0] = [512] * NumTestPoints
#                     p[:, 1] = range(0, 1024, 1024 / NumTestPoints)
#                     tp = self.Transform.ForwardRBFInstance.Transform(p)
# 
#                     self._draw_points(tp)
# 
#                 pyglet.gl.glColor4f(1.0, 1.0, 1.0, 1.0)
#                 gl.glDisable(gl.GL_BLEND)

    def CreateLabelVertexNumberBatch(self, verts):
        LabelBatch = pyglet.graphics.Batch()

        for i in range(0, verts.shape[0]):
            p = verts[i]
   #         l = pyglet.text.Label(text = str(i), font_name = 'Times New Roman', font_size = 36, x = p[0], y = p[1], color = (255, 255, 255, 255), width = 128, height = 128, anchor_x = 'center', anchor_y = 'center', batch = LabelBatch)

        return LabelBatch

    def draw_textures(self, ShowWarped=True, BoundingBox=None, z=None, glFunc=None):
        if self.ImageViewModel is None:
            return

        if ShowWarped:
            self.DrawWarpedImage(self.ImageViewModel, tex_color=None, BoundingBox=BoundingBox, z=z)
        else:
            self.DrawFixedImage(self.ImageViewModel, color=None, BoundingBox=BoundingBox, z=z)
