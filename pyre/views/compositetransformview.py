"""
Created on Oct 19, 2012

@author: u0490822
"""

from typing import Callable

import numpy

import nornir_imageregistration
from nornir_imageregistration.transforms import *
import numpy as np
from numpy.typing import NDArray

import OpenGL.GL as gl
import pyre.viewmodels
from pyre.viewmodels.transformcontroller import TransformController
from pyre.space import Space
from pyre.state import Action, IImageViewModelManager
from pyre.views.interfaces import IImageTransformView
from pyre.gl_engine import FrameBuffer
import pyre.gl_engine.shaders as shaders
from pyre.views import ImageTransformView


class CompositeTransformView(IImageTransformView):
    """
    Combines and image and a transform to render an image
    """
    _source_viewmodel_name: str  # The texture/image in the source space
    _target_viewmodel_name: str  # The texture/image in the target space
    _nameset: frozenset[str]  # The set of source and target names
    _source_image_view: IImageTransformView | None
    _target_image_view: IImageTransformView | None
    _transform_controller: TransformController
    _imageviewmodel_manager: IImageViewModelManager

    # These hold the rendered images for the source and target images.
    # These images are aligned if the transform aligns them.
    # A second pass rendering will blend the images together and draw to the back buffer
    _source_frame_buffer: FrameBuffer
    _target_frame_buffer: FrameBuffer

    _display_space: Space

    @property
    def display_space(self) -> Space:
        return self._display_space

    def _ClearVertexAngleDelta(self):
        self._transformVertexAngleDeltas = None
        self._vertexMaxAngleDelta = None
        self._MaxAngleDelta = None

    def _UpdateVertexAngleDelta(self, transform):
        self._transformVertexAngleDeltas = metrics.TriangleVertexAngleDelta(transform)
        self._vertexMaxAngleDelta = np.asarray(list(map(np.max, self._transformVertexAngleDeltas)))
        self._MaxAngleDelta = np.max(self._vertexMaxAngleDelta)
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
        return None if self._source_image_array is None else self._source_image_array.width

    @property
    def height(self) -> int:
        return None if self._source_image_array is None else self._source_image_array.height

    @property
    def fixedwidth(self) -> int | None:
        return None if self._source_image_array is None else self._source_image_array.width

    @property
    def fixedheight(self) -> int | None:
        return None if self._source_image_array is None else self._source_image_array.height

    @property
    def transform(self) -> nornir_imageregistration.ITransform:
        return self._transform_controller.TransformModel

    @property
    def transform_controller(self) -> TransformController:
        return self._transform_controller

    def __init__(self,
                 display_space: Space,
                 activate_context: Callable[[], None],
                 image_viewmodel_manager: IImageViewModelManager,
                 source_image_name: str,
                 target_image_name: str,
                 transform_controller: TransformController):
        """
        Constructor
        """
        self._display_space = display_space
        self._source_viewmodel_name = source_image_name
        self._target_viewmodel_name = target_image_name
        self._nameset = frozenset([source_image_name, target_image_name])

        self._imageviewmodel_manager = image_viewmodel_manager
        self._activate_context = activate_context
        # self._source_image_array = source_image_view
        # self._target_image_array = target_image_view
        self._transform_controller = transform_controller

        self._transformVertexAngleDeltas = None

        # imageFullPath = os.path.join(resources.ResourcePath(), "Point.png")
        # self.PointImage = pyglet.image.load(imageFullPath)
        # self.SelectedPointImage = pyglet.image.load(os.path.join(resources.ResourcePath(), "SelectedPoint.png"))

        # Valid Values are 'Add' and 'Subtract'
        self.ImageMode = 'Add'

        self._tranformed_verts_cache = None

        self._source_frame_buffer = FrameBuffer()
        self._target_frame_buffer = FrameBuffer()

        self._source_image_view = None
        self._target_image_view = None

        self._imageviewmodel_manager.add_change_event_listener(self.on_imageviewmodelmanager_change)

        # self._transform_controller.AddOnChangeEventListener(self.OnTransformChanged)

        # self._imageviewmodel_manager.add_change_event_listener(self.on_imageviewmodelmanager_change)

    def on_imageviewmodelmanager_change(self,
                                        name: str,
                                        action: Action,
                                        image: pyre.viewmodels.ImageViewModel):
        """Called when an imageviewmodel is added or removed from the manager"""
        print(
            f'* CompositeTransformView.on_imageviewmodelmanager_change {name} {action.value} self: {self._nameset}')
        if name not in self._nameset:
            print('\tDoes not match')
            return  # Not of interest to our class

        if action == Action.ADD:
            self._handle_add_imageviewmodel_event(name, image)
        elif action == Action.REMOVE:
            self._handle_remove_imageviewmodel_event(name)
        else:
            raise NotImplementedError()

    def _handle_add_imageviewmodel_event(self, name: str, image: pyre.viewmodels.ImageViewModel):
        """Process an add event from the imageviewmodel manager"""
        space_mapping = Space.Source if name == self._source_viewmodel_name else Space.Target
        view = ImageTransformView(space=space_mapping,
                                  activate_context=self._activate_context,
                                  image_view_model=image,
                                  transform_controller=self._transform_controller)
        print(f'Added image view model {name} to existing CompositeTransformView')

        if space_mapping == Space.Source:
            self._source_image_view = view
        elif space_mapping == Space.Target:
            self._target_image_view = view

        # self.center_camera()

    def _handle_remove_imageviewmodel_event(self, name: str):
        """Process a remove event from the imageviewmodel manager"""
        space_mapping = Space.Source if name == self._source_viewmodel_name else Space.Target
        if space_mapping == Space.Source:
            self._source_image_view = None
        elif space_mapping == Space.Target:
            self._target_image_view = None

    # def on_imageviewmodelmanager_change(self,
    #                                     name: str,
    #                                     action: Action,
    #                                     image: ImageViewModel):
    #     """Called when an imageviewmodel is added or removed from the manager"""
    #     print(
    #         f'* ImageTransformViewPanel.on_imageviewmodelmanager_change {name} {action.value} self: {self._config.imagenames}')
    #     if name not in self._nameset:
    #         print('\tDoes not match')
    #         return  # Not of interest to our class
    #
    #     if action == Action.ADD:
    #         self._handle_add_imageviewmodel_event(name, image)
    #     elif action == Action.REMOVE:
    #         self._handle_remove_imageviewmodel_event(name)
    #     else:
    #         raise NotImplementedError()
    #
    # def _handle_add_imageviewmodel_event(self, name: str, image: ImageViewModel):
    #     """Process an add event from the imageviewmodel manager"""
    #     # self._image_transform_view.image_view_model = image
    #     view = ImageTransformView(space=self.space,
    #                               activate_context=self.activate_context,
    #                               image_view_model=image,
    #                               transform_controller=self._config.transform_controller)
    #     print(f'Added image view model {name} to ImageTransformViewPanel')
    #     self._image_transform_view = view
    #
    #     self.center_camera()
    #
    # def _handle_remove_imageviewmodel_event(self, name: str):
    #     """Process a remove event from the imageviewmodel manager"""
    #     raise NotImplementedError()

    # def OnTransformChanged(self, transform_controller: TransformController):
    #
    #     #super(CompositeTransformView, self).OnTransformChanged(transform_controller)
    #
    #     self._tranformed_verts_cache = None
    #     #self._ClearVertexAngleDelta()
    #
    # def PopulateTransformedVertsCache(self):
    #     # verts = self.transform.WarpedPoints
    #     # self._tranformed_verts_cache = self.transform.transform(verts)
    #     if isinstance(self.Transform, nornir_imageregistration.IControlPoints):
    #         self._tranformed_verts_cache = self.Transform.TargetPoints
    #     return
    #
    # def RemoveTrianglesOutsideConvexHull(self, T, convex_hull):
    #     Triangles = np.array(T)
    #     if Triangles.ndim == 1:
    #         Triangles = Triangles.reshape(len(Triangles) / 3, 3)
    #
    #     convex_hull_flat = np.unique(convex_hull)
    #
    #     iTri = len(Triangles) - 1
    #     while iTri >= 0:
    #         tri = Triangles[iTri]
    #         if tri[0] in convex_hull_flat and tri[1] in convex_hull_flat and tri[2] in convex_hull_flat:
    #             # OK, find out if the midpoint of any lines are outside the convex hull
    #             Triangles = np.delete(Triangles, iTri, 0)
    #
    #         iTri -= 1
    #
    #     return Triangles

    def setup_composite_rendering(self):

        # gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
        # gl.glBlendColor(1.0,1.0,1.0,1.0)
        gl.glBlendFunc(gl.GL_ONE, gl.GL_ONE)
        return

    def clear_composite_rendering(self):
        # gl.glBlendFunc(gl.GL_SRC_COLOR, gl.GL_DST_COLOR)
        return

    def draw(self,
             view_proj: NDArray[np.floating],
             space: Space,
             client_size: tuple[int, int],
             bounding_box: nornir_imageregistration.Rectangle | None = None):
        """Draw the image in either source (fixed) or target (warped) space
        :param view_proj: View projection matrix
        :param client_size: Size of the client area in pixels. (height, width)"""

        # Rough idea:
        # 1. Render each image to a FrameBufferObject
        # 2. Render both FrameBufferObjects to the screen, blending the results according to the overlay type
        if self._source_image_view is not None and self._target_image_view is not None:

            source_fbo = self._source_frame_buffer.get_or_create_fbo(client_size)
            gl.glBindFramebuffer(gl.GL_FRAMEBUFFER, source_fbo)

            gl.glClearDepth(10000.0)
            gl.glClearColor(0, 0.1, 0, 1)
            gl.glClear(gl.GL_COLOR_BUFFER_BIT | gl.GL_DEPTH_BUFFER_BIT)

            self._source_image_view.draw(view_proj, space, client_size, bounding_box)

            target_fbo = self._target_frame_buffer.get_or_create_fbo(client_size)
            gl.glBindFramebuffer(gl.GL_FRAMEBUFFER, target_fbo)

            gl.glClearDepth(10000.0)
            gl.glClearColor(0, 0.1, 0, 1)
            gl.glClear(gl.GL_COLOR_BUFFER_BIT | gl.GL_DEPTH_BUFFER_BIT)

            self._target_image_view.draw(view_proj, space, client_size, bounding_box)

            gl.glBindFramebuffer(gl.GL_FRAMEBUFFER, 0)
            # OK, we have two textures with the rendered+transformed images of source and target images.
            # Inject textures into an overlay renderer and blend the images
            ortho_projection = pyre.ui.camera.Camera.orthogonal_projection(-1, 1,
                                                                           -1, 1,
                                                                           -1, 1)

            ortho_projection = np.identity(4)
            ortho_projection[0, 0] = 2.0
            ortho_projection[1, 1] = 2.0
            shaders.overlay_shader.draw(model_view_proj_matrix=ortho_projection,
                                        source_texture=self._source_frame_buffer.fbo_texture,
                                        target_texture=self._target_frame_buffer.fbo_texture,
                                        overlay_type=None,
                                        source_channel_mix=np.array([1.0, 0.0, 0.5, 1.0]),
                                        target_channel_mix=np.array([0.0, 1.0, 0.5, 1.0]))

        elif self._source_image_view is not None:
            self._source_image_view.draw(view_proj, space, client_size, bounding_box)
        elif self._target_image_view is not None:
            self._target_image_view.draw(view_proj, space, client_size, bounding_box)

    def draw_textures(self, view_proj: NDArray[np.floating],
                      space: Space,
                      BoundingBox=None,
                      glFunc=None):
        self.setup_composite_rendering()

        glFunc = gl.GL_FUNC_ADD

        gl.glEnable(gl.GL_BLEND)
        gl.glBlendFunc(gl.GL_SRC_COLOR, gl.GL_ONE_MINUS_SRC_COLOR)
        gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)

        if self._source_image_array is not None:
            FixedColor = None
            if glFunc == gl.GL_FUNC_ADD:
                FixedColor = (1.0, 0.0, 1.0, 1)

            # self.DrawFixedImage(view_proj, self.FixedImageArray, color=FixedColor, BoundingBox=BoundingBox, z=0.25)
            self.draw(view_proj=view_proj,
                      space=Space.Source,
                      BoundingBox=BoundingBox,
                      glFunc=glFunc)
            self.DrawWarpedImage(view_proj, self._source_image_array, tex_color=FixedColor, BoundingBox=BoundingBox,
                                 z=None,
                                 glFunc=glFunc,
                                 tween=1.0)

        gl.glClear(gl.GL_DEPTH_BUFFER_BIT)

        if self._target_image_array is not None:
            WarpedColor = None
            if glFunc == gl.GL_FUNC_ADD:
                gl.glBlendEquation(glFunc)
                WarpedColor = (0, 1.0, 0, 1)

            self.DrawWarpedImage(view_proj, self._target_image_array, tex_color=WarpedColor, BoundingBox=BoundingBox,
                                 z=None,
                                 glFunc=glFunc,
                                 tween=1)

        gl.glClear(gl.GL_DEPTH_BUFFER_BIT)
        self.clear_composite_rendering()
