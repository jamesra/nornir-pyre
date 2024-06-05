"""
Created on Oct 19, 2012

@author: u0490822
"""

import logging
import os

import nornir_imageregistration
from nornir_imageregistration.transforms import *
import numpy
from numpy.typing import NDArray
import scipy.spatial

import OpenGL.GL as gl
from pyre.views import imagetransformview
import pyre.views
from pyre.state.gl_context_manager import IGLContextManager


class CompositeTransformView(imagetransformview.ImageTransformView):
    """
    Combines and image and a transform to render an image
    """
    _fixed_image_array: pyre.viewmodels.ImageViewModel
    _warped_image_array: pyre.viewmodels.ImageViewModel
    _transform_controller: pyre.viewmodels.TransformController

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
            self._UpdateVertexAngleDelta(self._transform_controller)

        return self._transformVertexAngleDeltas

    @property
    def VertexMaxAngleDelta(self) -> float:
        return self._vertexMaxAngleDelta

    @property
    def NormalizedVertexMaxAngleDelta(self) -> float:
        return self._vertexMaxAngleDelta

    @property
    def MaxAngleDelta(self) -> float:
        return self._MaxAngleDelta

    @property
    def width(self) -> int:
        return None if self._fixed_image_array is None else self._fixed_image_array.width

    @property
    def height(self) -> int:
        return None if self._fixed_image_array is None else self._fixed_image_array.height

    @property
    def fixedwidth(self) -> int | None:
        return None if self._fixed_image_array is None else self._fixed_image_array.width

    @property
    def fixedheight(self) -> int | None:
        return None if self._fixed_image_array is None else self._fixed_image_array.height

    def __init__(self,
                 glcontexmanager: IGLContextManager,
                 FixedImageArray: pyre.viewmodels.ImageViewModel,
                 WarpedImageArray: pyre.viewmodels.ImageViewModel,
                 transform_controller: pyre.viewmodels.TransformController):
        """
        Constructor
        """
        super().__init__(space=pyre.Space.Composite,
                         glcontexmanager=glcontexmanager,
                         ImageViewModel=FixedImageArray,
                         transform_controller=transform_controller)

        self._fixed_image_array = FixedImageArray
        self._warped_image_array = WarpedImageArray
        self._transform_controller = transform_controller

        self._transformVertexAngleDeltas = None

        # imageFullPath = os.path.join(resources.ResourcePath(), "Point.png")
        # self.PointImage = pyglet.image.load(imageFullPath)
        # self.SelectedPointImage = pyglet.image.load(os.path.join(resources.ResourcePath(), "SelectedPoint.png"))

        # Valid Values are 'Add' and 'Subtract'
        self.ImageMode = 'Add'

        self._tranformed_verts_cache = None

    def OnTransformChanged(self, transform_controller: pyre.viewmodels.TransformController):

        super(CompositeTransformView, self).OnTransformChanged(transform_controller)

        self._tranformed_verts_cache = None
        self._ClearVertexAngleDelta()

    def PopulateTransformedVertsCache(self):
        # verts = self.transform.WarpedPoints
        # self._tranformed_verts_cache = self.transform.transform(verts)
        if isinstance(self.Transform, nornir_imageregistration.IControlPoints):
            self._tranformed_verts_cache = self.Transform.TargetPoints
        return

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

    def setup_composite_rendering(self):

        # gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
        # gl.glBlendColor(1.0,1.0,1.0,1.0)
        gl.glBlendFunc(gl.GL_ONE, gl.GL_ONE)
        return

    def clear_composite_rendering(self):
        # gl.glBlendFunc(gl.GL_SRC_COLOR, gl.GL_DST_COLOR)
        return

    def draw_textures(self, view_proj: NDArray[numpy.floating],
                      space: pyre.Space,
                      BoundingBox=None,
                      glFunc=None):
        self.setup_composite_rendering()

        glFunc = gl.GL_FUNC_ADD

        gl.glEnable(gl.GL_BLEND)
        gl.glBlendFunc(gl.GL_SRC_COLOR, gl.GL_ONE_MINUS_SRC_COLOR)
        gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)

        if self._fixed_image_array is not None:
            FixedColor = None
            if glFunc == gl.GL_FUNC_ADD:
                FixedColor = (1.0, 0.0, 1.0, 1)

            # self.DrawFixedImage(view_proj, self.FixedImageArray, color=FixedColor, BoundingBox=BoundingBox, z=0.25)
            self.draw(view_proj=view_proj,
                      space=pyre.Space.Source,
                      BoundingBox=BoundingBox,
                      glFunc=glFunc)
            self.DrawWarpedImage(view_proj, self._fixed_image_array, tex_color=FixedColor, BoundingBox=BoundingBox,
                                 z=None,
                                 glFunc=glFunc,
                                 tween=1.0)

        gl.glClear(gl.GL_DEPTH_BUFFER_BIT)

        if self._warped_image_array is not None:
            WarpedColor = None
            if glFunc == gl.GL_FUNC_ADD:
                gl.glBlendEquation(glFunc)
                WarpedColor = (0, 1.0, 0, 1)

            self.DrawWarpedImage(view_proj, self._warped_image_array, tex_color=WarpedColor, BoundingBox=BoundingBox,
                                 z=None,
                                 glFunc=glFunc,
                                 tween=1)

        gl.glClear(gl.GL_DEPTH_BUFFER_BIT)
        self.clear_composite_rendering()
