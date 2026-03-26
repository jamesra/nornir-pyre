"""
Created on Oct 19, 2012

@author: u0490822
"""
from typing import Callable

import OpenGL.GL as gl
import numpy as np
from numpy.typing import NDArray
from dependency_injector.wiring import Provide, inject

import nornir_imageregistration
from nornir_imageregistration.transforms import *
from pyre.gl_engine import FrameBuffer, raise_on_error  
from pyre.interfaces.action import Action
from pyre.interfaces.managers import IImageViewModelManager
from pyre.space import Space
from pyre.controllers.transformcontroller import TransformController
from pyre.views.interfaces import IImageTransformView
from pyre.container import IContainer
import pyre.qt_eventmanager
from pyre.gl_engine import shaders
from pyre.gl_engine.shaders.overlay_shader import OverlayType


from PyQt6.QtOpenGL import QOpenGLFunctions_4_1_Core as QOpenGLFunctions


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
    _gl_funcs: QOpenGLFunctions  # OpenGL functions for this context

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
    def VertexMaxAngleDelta(self) -> float | None:
        return float(self._vertexMaxAngleDelta) if self._vertexMaxAngleDelta is not None else None  # type: ignore[arg-type]

    @property
    def NormalizedVertexMaxAngleDelta(self) -> float | None:
        return float(self._vertexMaxAngleDelta) if self._vertexMaxAngleDelta is not None else None  # type: ignore[arg-type]

    @property
    def MaxAngleDelta(self) -> float | None:
        return self._MaxAngleDelta

    @property
    def width(self) -> int | None:
        return None if self._source_image_view is None else self._source_image_view.width

    @property
    def height(self) -> int | None:
        return None if self._source_image_view is None else self._source_image_view.height

    @property
    def fixedwidth(self) -> int | None:
        return None if self._source_image_view is None else self._source_image_view.width

    @property
    def fixedheight(self) -> int | None:
        return None if self._source_image_view is None else self._source_image_view.height

    @property
    def transform(self) -> nornir_imageregistration.ITransform:
        return self._transform_controller.TransformModel

    @property
    def transform_controller(self) -> TransformController:
        return self._transform_controller

    @property
    def gl(self) -> QOpenGLFunctions:
        """Set of OpenGL functions for the context this view operates within"""
        return self._gl_funcs

    @inject
    def __init__(self,
                 display_space: Space,
                 activate_context: Callable[[], None],
                 source_image_name: str,
                 target_image_name: str,
                 transform_controller: TransformController,
                 gl_funcs: QOpenGLFunctions,
                 image_viewmodel_manager: IImageViewModelManager = Provide[IContainer.imageviewmodel_manager],
                 ):
        """
        Constructor
        """
        self._gl_funcs = gl_funcs
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

        self._source_frame_buffer = FrameBuffer(gl_funcs)
        self._target_frame_buffer = FrameBuffer(gl_funcs)

        self._source_image_view = None
        self._target_image_view = None

        self._imageviewmodel_manager.add_change_event_listener(self.on_imageviewmodelmanager_change)

        # self._transform_controller.AddOnChangeEventListener(self.OnTransformChanged)

        # self._imageviewmodel_manager.add_change_event_listener(self.on_imageviewmodelmanager_change)

        if self._imageviewmodel_manager.__contains__(self._source_viewmodel_name):
            pyre.qt_eventmanager.qt_post_to_main(self._handle_add_imageviewmodel_event, self._source_viewmodel_name,
                                                 self._imageviewmodel_manager[self._source_viewmodel_name])

        if self._imageviewmodel_manager.__contains__(self._target_viewmodel_name):
            pyre.qt_eventmanager.qt_post_to_main(self._handle_add_imageviewmodel_event, self._target_viewmodel_name,
                                                 self._imageviewmodel_manager[
                                                     self._target_viewmodel_name])

    def __del__(self):
        try:
            self._imageviewmodel_manager.remove_change_event_listener(self.on_imageviewmodelmanager_change)
        except ValueError:  # Ignore if we've already been removed from the subscription list
            pass

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

        from pyre.views import ImageTransformView
        """Process an add event from the imageviewmodel manager"""
        space_mapping = Space.Source if name == self._source_viewmodel_name else Space.Target
        view = ImageTransformView(space=space_mapping,
                                  activate_context=self._activate_context,
                                  image_view_model=image,
                                  transform_controller=self._transform_controller,
                                  gl_funcs=self._gl_funcs)
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
        raise_on_error("after glBlendFunc in clear_composite_rendering")
        return

    def clear_composite_rendering(self):
        # gl.glBlendFunc(gl.GL_SRC_COLOR, gl.GL_DST_COLOR)
        return

    def draw(self,
             view_proj: NDArray[np.floating],
             space: Space,
             client_size: tuple[int, int],
             bounding_box: nornir_imageregistration.Rectangle | None = None,
             default_fbo: int | None = None,
             overlay_viewport_size: tuple[int, int] | None = None,
             show_mesh_lines: bool = False):
        """Draw the image in either source (fixed) or target (warped) space
        :param view_proj: View projection matrix
        :param client_size: Size of the client area in pixels. (height, width) logical.
        :param default_fbo: Widget's default framebuffer; must use this instead of 0 so overlay draws to QOpenGLWidget's internal FBO (Qt does not use FBO 0 for the widget).
        :param overlay_viewport_size: (width, height) in physical pixels for the overlay viewport; must match resizeGL so the composite fills the widget after resize/hi-DPI."""
        # Rough idea:
        # 1. Render each image to a FrameBufferObject
        # 2. Render both FrameBufferObjects to the screen, blending the results according to the overlay type
        if self._source_image_view is not None and self._target_image_view is not None:

            height, width = client_size
            
            source_fbo = self._source_frame_buffer.get_or_create_fbo(client_size)
            # Use raw OpenGL for framebuffer binding (Qt wrapper may not accept numpy.uintc)
            gl.glBindFramebuffer(gl.GL_FRAMEBUFFER, int(source_fbo))
            raise_on_error("after glBindFramebuffer(source) in compositetransformview.draw")
            
            # Set viewport to match framebuffer size
            gl.glViewport(0, 0, width, height)
            raise_on_error("after glViewport(source) in compositetransformview.draw")

            # Use glClearDepthf (not glClearDepth) - QOpenGLFunctions_4_1_Core uses the 'f' suffix
            gl.glClearDepthf(10000.0)
            raise_on_error("after glClearDepthf(source) in compositetransformview.draw")
            gl.glClearColor(0, 0.1, 0, 1)
            raise_on_error("after glClearColor(source) in compositetransformview.draw")
            gl.glClear(gl.GL_COLOR_BUFFER_BIT | gl.GL_DEPTH_BUFFER_BIT)  # type: ignore[operator]
            raise_on_error("after glClear(source) in compositetransformview.draw")

            # Both sub-views must use Space.Target (tween=1.0) so the source image is warped into
            # target space and aligns with the target image in the composite overlay.
            self._source_image_view.draw(view_proj, space, client_size, bounding_box,
                                         show_mesh_lines=show_mesh_lines)

            target_fbo = self._target_frame_buffer.get_or_create_fbo(client_size)
            # Use raw OpenGL for framebuffer binding (Qt wrapper may not accept numpy.uintc)
            gl.glBindFramebuffer(gl.GL_FRAMEBUFFER, int(target_fbo))
            raise_on_error("after glBindFramebuffer(target) in compositetransformview.draw")
            
            # Set viewport to match framebuffer size
            gl.glViewport(0, 0, width, height)
            raise_on_error("after glViewport(target) in compositetransformview.draw")

            # Use raw OpenGL for clear operations
            gl.glClearDepthf(10000.0)
            raise_on_error("after glClearDepthf(target) in compositetransformview.draw")
            gl.glClearColor(0, 0.1, 0, 1)
            raise_on_error("after glClearColor(target) in compositetransformview.draw")
            gl.glClear(gl.GL_COLOR_BUFFER_BIT | gl.GL_DEPTH_BUFFER_BIT)  # type: ignore[operator]
            raise_on_error("after glClear(target) in compositetransformview.draw")

            self._target_image_view.draw(view_proj, space, client_size, bounding_box,
                                         show_mesh_lines=show_mesh_lines)

            # Unbind our FBO and bind the widget's drawable. QOpenGLWidget does not use FBO 0;
            # it uses an internal FBO, so we must bind default_fbo (widget.defaultFramebufferObject()).
            draw_fbo = int(default_fbo) if default_fbo is not None else 0
            gl.glBindFramebuffer(gl.GL_FRAMEBUFFER, draw_fbo)
            raise_on_error("after glBindFramebuffer(draw target) in compositetransformview.draw")
            
            # Viewport must match resizeGL (physical pixels) so the overlay fills the widget after resize/hi-DPI.
            # Otherwise we only draw to logical size and the top/right stay green.
            ov_w, ov_h = overlay_viewport_size if overlay_viewport_size else (width, height)
            gl.glViewport(0, 0, ov_w, ov_h)
            raise_on_error("after glViewport(restore) in compositetransformview.draw")
            
            # OK, we have two textures with the rendered+transformed images of source and target images.
            # Inject textures into an overlay renderer and blend the images
            # ortho_projection = pyre.ui.camera.Camera.orthogonal_projection(-1, 1,
            #                                                                -1, 1,
            #                                                                -1, 1)

            # Use identity so the full-screen quad (vertices in [-1,1]) is drawn 1:1 in NDC and fills the viewport.
            # A non-identity scale (e.g. 2.0) would clip the quad and show only a central rectangle that can
            # appear to move at a different rate than the intended overlay.
            ortho_projection = np.identity(4, dtype=np.float32)

            # Validate framebuffer textures are valid
            if self._source_frame_buffer.fbo_texture == 0 or self._target_frame_buffer.fbo_texture == 0:
                print(f"Warning: Invalid framebuffer textures - source: {self._source_frame_buffer.fbo_texture}, target: {self._target_frame_buffer.fbo_texture}")
                return
            
            # Ensure overlay shader is initialized in this context (e.g. composite context added after first).
            # OverlayShader.initialized is a regular method (not a @property) - must call it with ().
            if not shaders.overlay_shader.initialized():
                try:
                    shaders.overlay_shader.initialize_gl_objects()
                except Exception:
                    pass
            if not shaders.overlay_shader.initialized():
                return

            # Depth test is only needed for tile overlap (Fixed/Warped). For the composite overlay
            # we draw a single full-screen blend on top, so disable depth so it always draws on top.
            gl.glDisable(gl.GL_DEPTH_TEST)
            gl.glDepthMask(gl.GL_FALSE)
            try:
                shaders.overlay_shader.draw(model_view_proj_matrix=ortho_projection,
                                            source_texture=self._source_frame_buffer.fbo_texture,
                                            target_texture=self._target_frame_buffer.fbo_texture,
                                            overlay_type=shaders.OverlayType.Tween,
                                            source_channel_mix=np.array([1.0, 0.0, 1.0, 1.0], dtype=np.float32),
                                            target_channel_mix=np.array([0.0, 1.0, 0.0, 1.0], dtype=np.float32))
            finally:
                gl.glDepthMask(gl.GL_TRUE)
                gl.glEnable(gl.GL_DEPTH_TEST)

        elif self._source_image_view is not None:
            self._source_image_view.draw(view_proj, space, client_size, bounding_box,
                                         show_mesh_lines=show_mesh_lines)
        elif self._target_image_view is not None:
            self._target_image_view.draw(view_proj, space, client_size, bounding_box,
                                         show_mesh_lines=show_mesh_lines)

    def draw_textures(self, view_proj: NDArray[np.floating],
                      space: Space,
                      BoundingBox=None,
                      glFunc=None):
        self.setup_composite_rendering()

        glFunc = gl.GL_FUNC_ADD

        from pyre.gl_engine.helpers import check_for_error
        gl.glEnable(gl.GL_BLEND)
        raise_on_error("after glEnable(GL_BLEND) in draw_textures")
        gl.glBlendFunc(gl.GL_SRC_COLOR, gl.GL_ONE_MINUS_SRC_COLOR)
        raise_on_error("after glBlendFunc(SRC_COLOR) in draw_textures")
        gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
        raise_on_error("after glBlendFunc(SRC_ALPHA) in draw_textures")

        if self._source_image_array is not None:  # type: ignore[attr-defined]
            FixedColor = None
            if glFunc == gl.GL_FUNC_ADD:
                FixedColor = (1.0, 0.0, 1.0, 1)

            # self.DrawFixedImage(view_proj, self.FixedImageArray, color=FixedColor, BoundingBox=BoundingBox, z=0.25)
            self.draw(view_proj=view_proj,  # type: ignore[call-arg]
                      space=Space.Source,
                      BoundingBox=BoundingBox,  # type: ignore[call-arg]
                      glFunc=glFunc)  # type: ignore[call-arg]
            self.DrawWarpedImage(view_proj, self._source_image_array, tex_color=FixedColor, BoundingBox=BoundingBox,  # type: ignore[attr-defined]
                                 z=None,
                                 glFunc=glFunc,
                                 tween=1.0)

        gl.glClear(gl.GL_DEPTH_BUFFER_BIT)
        raise_on_error("after glClear(DEPTH) in clear_composite_rendering")

        if self._target_image_array is not None:  # type: ignore[attr-defined]
            WarpedColor = None
            if glFunc == gl.GL_FUNC_ADD:
                gl.glBlendEquation(glFunc)
                raise_on_error("after glBlendEquation in clear_composite_rendering")
                WarpedColor = (0, 1.0, 0, 1)

            self.DrawWarpedImage(view_proj, self._target_image_array, tex_color=WarpedColor, BoundingBox=BoundingBox,  # type: ignore[attr-defined]
                                 z=None,
                                 glFunc=glFunc,
                                 tween=1)

        gl.glClear(gl.GL_DEPTH_BUFFER_BIT)
        raise_on_error("after glClear(DEPTH) in clear_composite_rendering")
        self.clear_composite_rendering()
