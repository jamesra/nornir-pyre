"""
Created on Oct 19, 2012

@author: u0490822
"""

from typing import Callable
import warnings

import OpenGL.GL as gl
import numpy as np
# from imageop import scale
from numpy.typing import NDArray

import nornir_imageregistration
import nornir_imageregistration.transforms.base
import nornir_imageregistration.transforms.triangulation
import pyre
from pyre.gl_engine import DynamicVAO, GLBuffer, GLIndexBuffer
import pyre.gl_engine.shaders as shaders
from pyre.space import Space
from pyre.views.gltiles import RenderCache, RenderDataMap, TileGLObjects
import pyre.views.gltiles as gltiles
from pyre.views.interfaces import IImageTransformView
from pyre.controllers.transformcontroller import TransformController


class ImageTransformView(IImageTransformView):
    """
    Combines an image and a transform to render an image.
    Images are divided into a grid of tiles.  Tiles are sized
    to fit within texture memory limits of the GPU.
    Read-only operations used for rendering the graphics.
    """

    _rendercache: RenderCache | None  # The cache of rendered data
    _z: float
    _image_viewmodel: pyre.viewmodels.ImageViewModel
    _image_mask_viewmodel: pyre.viewmodels.ImageViewModel | None
    _transform_controller: TransformController = None
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
    def transform_controller(self) -> TransformController:
        return self._transform_controller

    @transform_controller.setter
    def transform_controller(self, value: TransformController):
        if self._transform_controller is not None:
            self._transform_controller.RemoveOnChangeEventListener(self.OnTransformChanged)

        self._transform_controller = value

        if value is not None:
            if not isinstance(value, TransformController):
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
                 transform_controller: TransformController | None = None,
                 ):
        """
        Constructor
        :param imageviewmodel image_view_model: Textures for image
        :param transform transform_controller: nornir_imageregistration transform
        """
        self._activate_context = activate_context
        self._tile_render_data = {}
        self._image_space = space
        self._rendercache = RenderCache()
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

    def OnTransformChanged(self, transform_controller: TransformController):
        if self._gl_initialized:
            self.update_all_tile_buffers()

    def update_all_tile_buffers(self):
        """Update the buffers for all tiles in the image viewmodel"""
        unused_grid_coords = set(self._tile_render_data.keys())

        self._activate_context()

        if self._image_viewmodel is not None:
            for grid_coords in self._image_viewmodel.generate_grid_indicies():
                gltiles._update_tile_buffers(self.transform,
                                             grid_coords,
                                             self._image_viewmodel.TextureSize,
                                             self._image_space,
                                             get_or_create_tile_globjects=self.get_or_create_tile_globjects)
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

        triangles = []
        if not draw_in_fixed_space:
            if not isinstance(self.transform, nornir_imageregistration.transforms.ITriangulatedSourceSpace):
                return

            # Triangles = self.__Transform.WarpedTriangles
            verts = np.fliplr(self.transform.SourcePoints)
            triangles = self.transform.source_space_trianglulation
        else:
            if not isinstance(self.transform, nornir_imageregistration.transforms.ITriangulatedTargetSpace):
                return

            verts = np.fliplr(self.transform.TargetPoints)
            triangles = self.transform.target_space_trianglulation

        if verts is not None and triangles is not None:
            pyre.views.DrawTriangles(verts, triangles)

    @classmethod
    def _create_tile_globjects(cls) -> TileGLObjects:
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

    def get_or_create_tile_globjects(self, ix: int, iy: int) -> TileGLObjects:
        """Return the tile buffers for a grid coordinate, creating them if they do not exist"""
        if (ix, iy) not in self._tile_render_data:
            self._tile_render_data[(ix, iy)] = self._create_tile_globjects()

        return self._tile_render_data[(ix, iy)]

    def draw(self,
             view_proj: NDArray[np.floating],
             space: pyre.Space,
             client_size: tuple[int, int],
             bounding_box: nornir_imageregistration.Rectangle | None = None):
        """
        Draw the image in either source (fixed) or target (warped) space
        :param view_proj:
        :param space:
        :param client_size:
        :param bounding_box: Size of the client area in pixels. (height, width)
        :return:
        """

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

        tween = space

        for ix in range(0, image_viewmodel.NumCols):
            column = image_viewmodel.ImageArray[ix]
            for iy in range(0, image_viewmodel.NumRows):
                texture = column[iy]

                render_data = self.get_or_create_tile_globjects(ix, iy)

                shaders.texture_shader.draw(view_proj, texture, render_data.vao, tween=tween)
