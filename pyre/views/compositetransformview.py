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
from pyre.interfaces.viewtype import ViewType
from pyre.space import Space
from pyre.controllers.transformcontroller import TransformController
from pyre.perf_debug import timed
from pyre.views.composite_display import (
    COMPOSITE_SOURCE_CHANNEL_MIX,
    COMPOSITE_TARGET_CHANNEL_MIX,
)
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
                 image_viewmodel_manager: IImageViewModelManager = Provide[IContainer.image_viewmodel_manager],
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
        self._repaint_callback: Callable[[], None] | None = None

        self._imageviewmodel_manager.add_change_event_listener(self.on_imageviewmodelmanager_change)

        # Sub-views subscribe to TransformController OnChange themselves; also expose
        # OnTransformChanged so model-replace handlers on the panel can force a rebuild.
        # self._transform_controller.AddOnChangeEventListener(self.OnTransformChanged)

        # self._imageviewmodel_manager.add_change_event_listener(self.on_imageviewmodelmanager_change)

        if self._imageviewmodel_manager.__contains__(self._source_viewmodel_name):
            pyre.qt_eventmanager.qt_post_to_main(self._handle_add_imageviewmodel_event, self._source_viewmodel_name,
                                                 self._imageviewmodel_manager[self._source_viewmodel_name])

        if self._imageviewmodel_manager.__contains__(self._target_viewmodel_name):
            pyre.qt_eventmanager.qt_post_to_main(self._handle_add_imageviewmodel_event, self._target_viewmodel_name,
                                                 self._imageviewmodel_manager[
                                                     self._target_viewmodel_name])

    def OnTransformChanged(self, transform_controller: TransformController | None = None) -> None:
        """Forward model/replace refreshes to composite source and target sub-views."""
        for sub_view in (self._source_image_view, self._target_image_view):
            if sub_view is not None:
                sub_view.OnTransformChanged(transform_controller)

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
        view = ImageTransformView(
            space=space_mapping,
            activate_context=self._activate_context,
            image_view_model=image,
            transform_controller=self._transform_controller,
            gl_funcs=self._gl_funcs,
            # Composite source must build the full deformable mesh; display-space
            # budgeted/lazy fills leave the magenta FBO empty (tiles built off-camera
            # first, and continuation often never catches up). Target stays static quads.
            eager_tile_meshes=(space_mapping == Space.Source),
            # Only the source FBO needs a deformable mesh; target stays native quads.
            warp_into_target_display=(space_mapping == Space.Source),
        )
        view._repaint_callback = self._repaint_callback

        if space_mapping == Space.Source:
            self._source_image_view = view
            self._source_frame_buffer.invalidate_color()
        elif space_mapping == Space.Target:
            self._target_image_view = view
            self._target_frame_buffer.invalidate_color()

        if self._source_image_view is not None and self._target_image_view is not None:
            if self._repaint_callback is not None:
                self._repaint_callback()

        # self.center_camera()

    def _handle_remove_imageviewmodel_event(self, name: str):
        """Process a remove event from the imageviewmodel manager"""
        space_mapping = Space.Source if name == self._source_viewmodel_name else Space.Target
        if space_mapping == Space.Source:
            self._source_image_view = None
        elif space_mapping == Space.Target:
            self._target_image_view = None

    def create_objects(self) -> None:
        """Initialize GL objects on composite sub-views when the panel context is ready."""
        for sub_view in (self._source_image_view, self._target_image_view):
            if sub_view is not None:
                sub_view.create_objects()  # type: ignore[attr-defined]

    def _fill_composite_layer_fbo(
            self,
            frame_buffer: FrameBuffer,
            sub_view: IImageTransformView,
            view_proj: NDArray[np.floating],
            space: Space,
            fbo_size: tuple[int, int],
            ov_w: int,
            ov_h: int,
            bounding_box: nornir_imageregistration.Rectangle | None,
            show_mesh_lines: bool,
            rigid_composite_source_align: bool) -> None:
        """Rasterize one composite image layer into its retained FBO."""
        layer_fbo = frame_buffer.get_or_create_fbo(fbo_size)
        gl.glBindFramebuffer(gl.GL_FRAMEBUFFER, int(layer_fbo))
        raise_on_error("after glBindFramebuffer(layer) in compositetransformview._fill_composite_layer_fbo")
        gl.glViewport(0, 0, ov_w, ov_h)
        raise_on_error("after glViewport(layer) in compositetransformview._fill_composite_layer_fbo")
        gl.glDisable(gl.GL_DEPTH_TEST)
        gl.glDepthMask(gl.GL_FALSE)
        try:
            gl.glClearColor(0, 0.1, 0, 1)
            raise_on_error("after glClearColor(layer) in compositetransformview._fill_composite_layer_fbo")
            gl.glClear(gl.GL_COLOR_BUFFER_BIT)  # type: ignore[operator]
            raise_on_error("after glClear(layer) in compositetransformview._fill_composite_layer_fbo")
            sub_view.draw(view_proj, space, fbo_size, bounding_box,
                          show_mesh_lines=show_mesh_lines,
                          rigid_composite_source_align=rigid_composite_source_align,
                          view_type=ViewType.Composite)
        finally:
            gl.glDepthMask(gl.GL_TRUE)
            gl.glEnable(gl.GL_DEPTH_TEST)
        image_vm = getattr(sub_view, "image_view_model", None)
        if image_vm is not None and bool(getattr(image_vm, "_ImageArray", None)):
            frame_buffer.mark_color_valid()

    def draw(self,
             view_proj: NDArray[np.floating],
             space: Space,
             client_size: tuple[int, int],
             bounding_box: nornir_imageregistration.Rectangle | None = None,
             default_fbo: int | None = None,
             overlay_viewport_size: tuple[int, int] | None = None,
             show_mesh_lines: bool = False,
             rigid_composite_source_align: bool = False,
             view_type: ViewType | None = None,
             refill_source_layer: bool = True,
             refill_target_layer: bool = True):
        """Draw the image in either source (fixed) or target (warped) space
        :param view_proj: View projection matrix
        :param client_size: Size of the client area in pixels. (height, width) logical.
        :param default_fbo: Widget's default framebuffer; must use this instead of 0 so overlay draws to QOpenGLWidget's internal FBO (Qt does not use FBO 0 for the widget).
        :param overlay_viewport_size: (width, height) in physical pixels for the overlay viewport; must match resizeGL so the composite fills the widget after resize/hi-DPI.
        :param refill_source_layer: When False, reuse the retained source FBO if it is still valid.
        :param refill_target_layer: When False, reuse the retained target FBO if it is still valid.
        """
        # Rough idea:
        # 1. Render each image to a FrameBufferObject
        # 2. Render both FrameBufferObjects to the screen, blending the results according to the overlay type
        if self._source_image_view is not None and self._target_image_view is not None:
            interactive = self._transform_controller.interactive_edit_in_progress
            if interactive:
                show_mesh_lines = False

            with timed('composite_transform_draw'):
                self._activate_context()
                height, width = client_size
                ov_w, ov_h = overlay_viewport_size if overlay_viewport_size else (width, height)
                fbo_size = (ov_h, ov_w)

                for sub_view, frame_buffer in (
                        (self._source_image_view, self._source_frame_buffer),
                        (self._target_image_view, self._target_frame_buffer),
                ):
                    if sub_view is None:
                        continue
                    image_vm = sub_view.image_view_model  # type: ignore[attr-defined]
                    if image_vm is None:
                        continue
                    had_textures = bool(getattr(image_vm, "_ImageArray", None))
                    _ = image_vm.ImageArray
                    if bool(getattr(image_vm, "_ImageArray", None)) and not had_textures:
                        frame_buffer.invalidate_color()

                self._source_frame_buffer.get_or_create_fbo(fbo_size)
                if refill_source_layer or not self._source_frame_buffer.color_valid:
                    self._fill_composite_layer_fbo(
                        self._source_frame_buffer,
                        self._source_image_view,
                        view_proj,
                        Space.Source,
                        fbo_size,
                        ov_w,
                        ov_h,
                        bounding_box,
                        show_mesh_lines,
                        True)

                self._target_frame_buffer.get_or_create_fbo(fbo_size)
                if refill_target_layer or not self._target_frame_buffer.color_valid:
                    self._fill_composite_layer_fbo(
                        self._target_frame_buffer,
                        self._target_image_view,
                        view_proj,
                        Space.Target,
                        fbo_size,
                        ov_w,
                        ov_h,
                        bounding_box,
                        show_mesh_lines,
                        False)

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
                                                source_channel_mix=COMPOSITE_SOURCE_CHANNEL_MIX,
                                                target_channel_mix=COMPOSITE_TARGET_CHANNEL_MIX)
                finally:
                    gl.glDepthMask(gl.GL_TRUE)
                    gl.glEnable(gl.GL_DEPTH_TEST)

        elif self._source_image_view is not None:
            self._source_image_view.draw(view_proj, space, client_size, bounding_box,
                                         show_mesh_lines=show_mesh_lines,
                                         view_type=view_type)
        elif self._target_image_view is not None:
            self._target_image_view.draw(view_proj, space, client_size, bounding_box,
                                         show_mesh_lines=show_mesh_lines,
                                         view_type=view_type)
