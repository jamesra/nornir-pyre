'''
Created on Oct 19, 2012

@author: u0490822
'''

import logging
import os

import nornir_imageregistration
from nornir_imageregistration.transforms import *
import numpy
from numpy.typing import NDArray
import scipy.spatial

import OpenGL.GL as gl
from pyre.views import imagegridtransformview
import pyre.views


class CompositeTransformView(imagegridtransformview.ImageGridTransformView):
    '''
    Combines and image and a transform to render an image
    '''

    def _ClearVertexAngleDelta(self):
        self._transformVertexAngleDeltas = None
        self._vertexMaxAngleDelta = None
        self._MaxAngleDelta = None

    def _UpdateVertexAngleDelta(self, transform):
        self._transformVertexAngleDeltas = metrics.TriangleVertexAngleDelta(transform)
        self._vertexMaxAngleDelta = numpy.asarray(list(map(numpy.max, self._transformVertexAngleDeltas)))
        self._MaxAngleDelta = numpy.max(self._vertexMaxAngleDelta)
        if self._MaxAngleDelta != 0:
            self._normalized_vertex_max_angle_delta = self._vertexMaxAngleDelta / self._MaxAngleDelta
        else:
            self._normalized_vertex_max_angle_delta = self._vertexMaxAngleDelta

    @property
    def TransformVertexAngleDelta(self):
        if self._transformVertexAngleDeltas is None:
            self._UpdateVertexAngleDelta(self.TransformController)

        return self._transformVertexAngleDeltas

    @property
    def VertexMaxAngleDelta(self):
        return self._vertexMaxAngleDelta

    @property
    def NormalizedVertexMaxAngleDelta(self):
        return self._vertexMaxAngleDelta

    @property
    def MaxAngleDelta(self):
        return self._MaxAngleDelta

    @property
    def width(self):
        if self.FixedImageArray is None:
            return None
        return self.FixedImageArray.width

    @property
    def height(self):
        if self.FixedImageArray is None:
            return None
        return self.FixedImageArray.height

    @property
    def fixedwidth(self):
        if self.FixedImageArray is None:
            return None
        return self.FixedImageArray.width

    @property
    def fixedheight(self):
        if self.FixedImageArray is None:
            return None
        return self.FixedImageArray.height

    def __init__(self, FixedImageArray: pyre.viewmodels.ImageViewModel,
                 WarpedImageArray: pyre.viewmodels.ImageViewModel,
                 Transform: pyre.viewmodels.TransformController):
        '''
        Constructor
        '''
        super(CompositeTransformView, self).__init__(ImageViewModel=FixedImageArray, Transform=Transform)

        self.FixedImageArray = FixedImageArray
        self.WarpedImageArray = WarpedImageArray
        self.TransformController = Transform

        self._transformVertexAngleDeltas = None

        # imageFullPath = os.path.join(resources.ResourcePath(), "Point.png")
        # self.PointImage = pyglet.image.load(imageFullPath)
        # self.SelectedPointImage = pyglet.image.load(os.path.join(resources.ResourcePath(), "SelectedPoint.png"))

        # Valid Values are 'Add' and 'Subtract'
        self.ImageMode = 'Add'

        self._tranformed_verts_cache = None

    def OnTransformChanged(self):

        super(CompositeTransformView, self).OnTransformChanged()

        self._tranformed_verts_cache = None
        self._ClearVertexAngleDelta()

    def PopulateTransformedVertsCache(self):
        # verts = self.Transform.WarpedPoints
        # self._tranformed_verts_cache = self.Transform.Transform(verts)
        if isinstance(self.Transform, nornir_imageregistration.IControlPoints):
            self._tranformed_verts_cache = self.Transform.TargetPoints
        return

    def draw_points(self, ForwardTransform=True, SelectedIndex=None, FixedSpace=True, BoundingBox=None, ScaleFactor=1):
        # if(ForwardTransform):

        if self.TransformController is None:
            return

        if self._tranformed_verts_cache is None:
            self.PopulateTransformedVertsCache()

        # if self._vertexMaxAngleDelta is None:
        #    self._UpdateVertexAngleDelta(self.TransformController)

        if not self._tranformed_verts_cache is None:
            self._draw_points(self._tranformed_verts_cache, SelectedIndex, BoundingBox=BoundingBox,
                              ScaleFactor=ScaleFactor)

    def RemoveTrianglesOutsideConvexHull(self, T, convex_hull):
        Triangles = numpy.array(T)
        if Triangles.ndim == 1:
            Triangles = Triangles.reshape(len(Triangles) / 3, 3)

        convex_hull_flat = numpy.unique(convex_hull)

        iTri = len(Triangles) - 1
        while iTri >= 0:
            tri = Triangles[iTri]
            if tri[0] in convex_hull_flat and tri[1] in convex_hull_flat and tri[2] in convex_hull_flat:
                # OK, find out if the midpoint of any lines are outside the convex hull
                Triangles = numpy.delete(Triangles, iTri, 0)

            iTri -= 1

        return Triangles

    #
    #     def draw_lines(self, ForwardTransform=True):
    #         if(self.TransformController is None):
    #             return
    #
    #         pyglet.gl.glColor4f(1.0, 0, 0, 1.0)
    #         ImageArray = self.WarpedImageArray
    #         for ix in range(0, ImageArray.NumCols):
    #             for iy in range(0, ImageArray.NumRows):
    #                 x = ImageArray.TextureSize[1] * ix
    #                 y = ImageArray.TextureSize[0] * iy
    #                 h, w = ImageArray.TextureSize
    #
    #                 WarpedCorners = [[y, x],
    #                                 [y, x + w],
    #                                 [y + h, x],
    #                                 [y + h, x + w]]
    #
    #                 FixedCorners = self.TransformController.Transform(WarpedCorners)
    #
    #                 tri = scipy.spatial.Delaunay(FixedCorners)
    #                 LineIndicies = pyre.views.LineIndiciesFromTri(tri.vertices)
    #
    #                 FlatPoints = numpy.fliplr(FixedCorners).ravel().tolist()
    #
    #                 vertarray = (gl.GLfloat * len(FlatPoints))(*FlatPoints)
    #
    #                 gl.glDisable(gl.GL_TEXTURE_2D)
    #
    #                 pyglet.graphics.draw_indexed(len(vertarray) / 2,
    #                                                          gl.GL_LINES,
    #                                                          LineIndicies,
    #                                                          ('v2f', vertarray))
    #         pyglet.gl.glColor4f(1.0, 1.0, 1.0, 1.0)

    def setup_composite_rendering(self):

        # gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
        # gl.glBlendColor(1.0,1.0,1.0,1.0)
        gl.glBlendFunc(gl.GL_ONE, gl.GL_ONE)
        return

    def clear_composite_rendering(self):
        # gl.glBlendFunc(gl.GL_SRC_COLOR, gl.GL_DST_COLOR)
        return

    def draw_textures(self, view_proj: NDArray[numpy.floating], BoundingBox=None, glFunc=None):
        self.setup_composite_rendering()

        glFunc = gl.GL_FUNC_ADD

        if self.FixedImageArray is not None:
            FixedColor = None
            if glFunc == gl.GL_FUNC_ADD:
                FixedColor = (1.0, 0.0, 1.0, 1)

            # self.DrawFixedImage(view_proj, self.FixedImageArray, color=FixedColor, BoundingBox=BoundingBox, z=0.25)
            self.DrawWarpedImage(view_proj, self.WarpedImageArray, tex_color=FixedColor, BoundingBox=BoundingBox,
                                 z=0.25,
                                 glFunc=glFunc)

        if self.WarpedImageArray is not None:
            WarpedColor = None
            if glFunc == gl.GL_FUNC_ADD:
                gl.glBlendEquation(glFunc)
                WarpedColor = (0, 1.0, 0, 1)

            self.DrawWarpedImage(view_proj, self.WarpedImageArray, tex_color=WarpedColor, BoundingBox=BoundingBox,
                                 z=0.75,
                                 glFunc=glFunc)

        self.clear_composite_rendering()
        # self.DrawFixedImage(self.__WarpedImageArray)
        # self._draw_warped_image(self.__FixedImageArray)
