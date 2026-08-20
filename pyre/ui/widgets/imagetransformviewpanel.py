"""
Created on Oct 16, 2012

@author: u0490822
"""
from __future__ import annotations
from dataclasses import dataclass
import warnings

import PyQt6.QtGui
import numpy as np

import OpenGL.GL as gl
from PyQt6.QtWidgets import QWidget, QLabel
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QWheelEvent, QMouseEvent, QResizeEvent

from dependency_injector.wiring import Provide
from dependency_injector.providers import Factory, Dict
import nornir_imageregistration
from nornir_imageregistration import ITransform
from pyre.interfaces import ICommand
from pyre.interfaces import ControlPointAction

from pyre.observable import ObservableSet
from pyre.interfaces.action import Action
from pyre.interfaces.managers import ICommandQueue, IGLContextManager
from pyre.interfaces.managers.image_viewmodel_manager import IImageViewModelManager
from pyre.interfaces.managers.transform_controller_glbuffer_manager import ITransformControllerGLBufferManager, \
    BufferType
import pyre.interfaces.managers.gl_context_manager
from pyre.settings import AppSettings
from pyre.space import Space
from pyre.state.managers.command_queue import CommandQueue

from pyre.ui.widgets import imagetransformpanelbase
from pyre.controllers.transformcontroller import TransformController
from pyre.gl_engine import FrameBuffer
from pyre.gl_engine.framebuffer import blit_framebuffer_color
from pyre.views import (ClearDrawTextureState, CompositeTransformView, PointView, ImageTransformView,
                        SetDrawTextureState)
from pyre.views.interfaces import IImageTransformView
from pyre.container import IContainer
from nornir_imageregistration.transforms.transform_type import TransformType
from pyre.interfaces.viewtype import ViewType
from pyre.views.transformcontrollerview import BinarySelectionMapper, TransformControllerView
from pyre.viewmodels.controlpointmap import ControlPointMap
from pyre.transform_edit_policy import source_panel_hint_message, rigid_rotation_locked
from pyre.views.composite_display import (
    camera_lookat_from_target_space,
    composite_control_point_draw_rows,
    composite_legend_rich_text,
    resolve_composite_display_draw_params,
)


@dataclass
class ImageTransformPanelConfig:
    glcontext_manager: pyre.interfaces.managers.gl_context_manager.IGLContextManager
    transform_controller: TransformController
    transformglbuffer_manager: ITransformControllerGLBufferManager
    imageviewmodel_manager: IImageViewModelManager
    view_type: ViewType  # Type of view to display
    imagename_space_mapping: dict[str, Space]  # Maps an image name to a space


class ImageTransformViewPanel(imagetransformpanelbase.ImageTransformPanelBase):
    """
    The main editing control for a transform.
    """
    _settings: AppSettings = Provide[IContainer.settings]

    _CurrentDragPoint: int | None = None
    _HighlightedPointIndex: int | None = 0
    _space: pyre.Space
    _image_transform_view: IImageTransformView | None = None  # The transformed image
    _show_lines: bool = False
    _image_layer_dirty: bool = True
    _retained_image_buffer: FrameBuffer | None = None
    _config: ImageTransformPanelConfig

    _command: ICommand | None
    _command_queue: CommandQueue
    _transform_controller: TransformController

    _imageviewmodel_manager: IImageViewModelManager = Provide[IContainer.image_viewmodel_manager]
    _glcontext_manager: IGLContextManager = Provide[IContainer.glcontext_manager]
    _transformglbuffer_manager: ITransformControllerGLBufferManager = Provide[IContainer.transform_gl_buffer_manager]

    _view_type: ViewType
    _transform_type_to_command_action_map: dict[TransformType, dict[ControlPointAction, Factory]] = Provide[  # type: ignore[assignment]
        IContainer.action_command_map]

    _imagename_space_mapping: dict[str, Space]  # Maps an image name to a space

    _transform_controller_view: TransformControllerView | None

    _fixed_layer_hint: QLabel | None = None
    _composite_legend: QLabel | None = None

    _selected_points: ObservableSet[int]  # The indices of the selected points

    @property
    def control_point_scale(self) -> float:
        """Determines how large control points are rendered"""
        return self._settings.ui.control_point_search_radius

    @property
    def imagename_space_mapping(self) -> dict[str, Space]:
        """Maps an image name to a space"""
        return self._imagename_space_mapping

    @property
    def view_type(self) -> ViewType:
        return self._view_type

    @property
    def show_lines(self) -> bool:
        return self._show_lines

    @show_lines.setter
    def show_lines(self, value: bool):
        if self._show_lines == value:
            return
        self._show_lines = value
        self.mark_image_layer_dirty()

    @property
    def space(self) -> pyre.Space:
        """Which space the image is rendered in, Target or Source space"""
        return self._space

    @property
    def FixedSpace(self) -> bool:
        warnings.warn("FixedSpace is deprecated.  Use space instead")
        return self._space == pyre.Space.Source

    @property
    def SelectedPointIndex(self) -> int | None:
        return ImageTransformViewPanel._CurrentDragPoint

    @SelectedPointIndex.setter
    def SelectedPointIndex(self, value: int | None):
        ImageTransformViewPanel._CurrentDragPoint = value

        if value is not None:
            ImageTransformViewPanel._HighlightedPointIndex = value

        print(
            f'Set Selected Point Index {value} cdp: {ImageTransformViewPanel._CurrentDragPoint} hpi: {ImageTransformViewPanel._HighlightedPointIndex}')

    @property
    def transform(self) -> nornir_imageregistration.ITransform:
        return self._transform_controller.TransformModel

    @property
    def transform_controller(self) -> TransformController:
        return self._transform_controller

    @property
    def image_transform_view(self) -> IImageTransformView | None:
        return self._image_transform_view

    @image_transform_view.setter
    def image_transform_view(self, value: IImageTransformView):
        self._image_transform_view = value

    @property
    def max_image_dimension(self):
        assert self.image_transform_view is not None
        return max([self.image_transform_view.width, self.image_transform_view.height])  # type: ignore[arg-type]

    def __init__(self,
                 parent: QWidget,
                 space: Space,
                 view_type: ViewType,
                 transform_controller: TransformController,
                 imagename_space_mapping: dict[str, Space],
                 selected_points: ObservableSet[int],
                 **kwargs):
        """
        Constructor
        :param space:
        """
        self._selected_points = selected_points
        self._command = None  # type: ignore[assignment]
        self._transform_controller_view = None  # type: ignore[assignment]
        self._imagename_space_mapping = imagename_space_mapping
        self._view_type = view_type
        self._transform_controller = transform_controller
        self._space = space
        self._command_queue = CommandQueue()  # type: ignore[assignment]

        super().__init__(parent=parent,
                         transform_controller=transform_controller,
                         **kwargs)

        # Create a timer for periodic updates
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.on_timer)

        self.ShowWarped = False
        self.glFunc = gl.GL_FUNC_ADD
        self.LastDrawnBoundingBox = None

        self._image_transform_view = None
        self._image_layer_dirty = True
        self._retained_image_buffer = None

        self.DebugTickCounter = 0
        # Use singleShot timer that reschedules itself instead of repeating timer
        # This works around a Qt issue where repeating timers stop firing
        QTimer.singleShot(100, self.on_timer_singleshot)

        self.statusbar.space = self.space

        self._imageviewmodel_manager.add_change_event_listener(self.on_imageviewmodelmanager_change)

        # Subscribe directly to context activation events
        self.subscribe_context_activation(self._glcontext_manager)

        transform_controller.AddOnModelReplacedEventListener(self._on_transform_model_changed)
        transform_controller.AddOnChangeEventListener(self._on_transform_controller_changed)

        if self._view_type == ViewType.Source and self._space == Space.Source:
            self._fixed_layer_hint = QLabel(self)
            self._fixed_layer_hint.setStyleSheet(
                "QLabel { background-color: rgba(255, 255, 255, 210); color: black; padding: 4px 8px; }")
            self._fixed_layer_hint.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            self._fixed_layer_hint.hide()
            self._update_layer_policy_hints()
        elif self._view_type == ViewType.Target and self._space == Space.Target:
            self._warped_layer_hint = QLabel(self)
            self._warped_layer_hint.setText(
                "Rigid transform — translate here; rotate in Composite view (Ctrl+scroll)")
            self._warped_layer_hint.setStyleSheet(
                "QLabel { background-color: rgba(255, 255, 255, 210); color: black; padding: 4px 8px; }")
            self._warped_layer_hint.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            self._warped_layer_hint.hide()
            self._update_layer_policy_hints()
        elif self._view_type == ViewType.Composite:
            self._composite_legend = QLabel(self)
            self._composite_legend.setTextFormat(Qt.TextFormat.RichText)
            self._composite_legend.setText(composite_legend_rich_text())
            self._composite_legend.setStyleSheet(
                "QLabel { background-color: rgba(0, 0, 0, 160); padding: 4px 8px; }")
            self._composite_legend.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            self._composite_legend.adjustSize()
            self._position_composite_legend()
            self._composite_legend.show()
            self._composite_legend.raise_()

    def _update_layer_policy_hints(self) -> None:
        """Show corner hints when transform-edit policy blocks actions in this panel."""
        if getattr(self, '_fixed_layer_hint', None) is not None:
            msg = source_panel_hint_message(
                self._transform_controller.TransformModel,
                self._transform_controller.type,
                self._space,
                self._view_type)
            if msg is not None:
                self._fixed_layer_hint.setText(msg)
                self._fixed_layer_hint.adjustSize()
                self._fixed_layer_hint.move(8, 8)
                self._fixed_layer_hint.show()
                self._fixed_layer_hint.raise_()
            else:
                self._fixed_layer_hint.hide()
        if getattr(self, '_warped_layer_hint', None) is not None:
            if rigid_rotation_locked(self._transform_controller.type, self._view_type):
                self._warped_layer_hint.adjustSize()
                self._warped_layer_hint.move(8, 8)
                self._warped_layer_hint.show()
                self._warped_layer_hint.raise_()
            else:
                self._warped_layer_hint.hide()

    def _update_fixed_layer_hint(self) -> None:
        """Backward-compatible alias for layer policy hint refresh."""
        self._update_layer_policy_hints()

    def _position_composite_legend(self) -> None:
        """Anchor the composite source/target legend in the top-right corner."""
        if self._composite_legend is None:
            return
        self._composite_legend.adjustSize()
        margin = 8
        self._composite_legend.move(
            max(margin, self.width() - self._composite_legend.width() - margin),
            margin,
        )

    def on_resize(self, event: QResizeEvent) -> None:
        """Handle resize and keep overlay hints anchored."""
        super().on_resize(event)
        if getattr(self, '_fixed_layer_hint', None) is not None and self._fixed_layer_hint.isVisible():
            self._fixed_layer_hint.move(8, 8)
        if getattr(self, '_warped_layer_hint', None) is not None and self._warped_layer_hint.isVisible():
            self._warped_layer_hint.move(8, 8)
        self._position_composite_legend()

    def __del__(self):
        try:
            self._imageviewmodel_manager.remove_change_event_listener(self.on_imageviewmodelmanager_change)
        except ValueError:
            pass

        try:
            self._transform_controller.RemoveOnModelReplacedEventListener(self._on_transform_model_changed)
        except ValueError:
            pass

        try:
            self._transform_controller.RemoveOnChangeEventListener(self._on_transform_controller_changed)
        except ValueError:
            pass

    def _composite_deferred_redraw(self) -> None:
        """Refill composite overlay FBOs after sub-view GL objects catch up."""
        self.mark_image_layer_dirty()
        self._glpanel.update()

    def mark_image_layer_dirty(self) -> None:
        """Request a full texture-layer redraw on the next paint."""
        self._image_layer_dirty = True

    def _ensure_retained_image_buffer(self) -> FrameBuffer:
        """Return the Source/Target panel background FBO, creating it on first use."""
        if self._retained_image_buffer is None:
            self._retained_image_buffer = FrameBuffer(self._glpanel.gl_funcs)
        return self._retained_image_buffer

    def _draw_retained_image_layer(
            self,
            view_proj: np.ndarray,
            draw_kwargs: dict[str, object],
            default_fbo: int,
            ov_w: int,
            ov_h: int,
            refill: bool) -> None:
        """Draw or blit the retained Source/Target image background."""
        if self._image_transform_view is None:
            return
        fbo_size = (ov_h, ov_w)
        buffer = self._ensure_retained_image_buffer()
        layer_fbo = buffer.get_or_create_fbo(fbo_size)
        if refill or not buffer.color_valid:
            gl.glBindFramebuffer(gl.GL_FRAMEBUFFER, int(layer_fbo))
            gl.glViewport(0, 0, ov_w, ov_h)
            gl.glClearColor(0, 0.1, 0, 1)
            gl.glClear(gl.GL_COLOR_BUFFER_BIT)
            self._image_transform_view.draw(view_proj, **draw_kwargs)
            buffer.mark_color_valid()
        blit_framebuffer_color(int(layer_fbo), int(default_fbo), ov_w, ov_h)
        gl.glViewport(0, 0, ov_w, ov_h)

    def _image_layer_dirty_for_transform(self, _controller: TransformController) -> bool:
        """True when a transform change alters visible image pixels in this panel."""
        if self.view_type == ViewType.Composite:
            return True
        return self.show_lines

    def _on_transform_controller_changed(self, controller: TransformController) -> None:
        """Repaint when registration or display overlays change in another STOS view."""
        if self._image_layer_dirty_for_transform(controller):
            self.mark_image_layer_dirty()
        self._glpanel.update()

    def _on_transform_model_changed(self,
                                    controller: TransformController,
                                    old: ITransform | None,
                                    new: ITransform):
        """Called when the model in the transform controller changes.  This is not called when the
        transform is modified, only when the model is replaced"""
        self._update_fixed_layer_hint()
        # Force tile/control-point redraw even if a coalesced OnChange was dropped.
        image_view = self._image_transform_view
        if image_view is not None:
            on_changed = getattr(image_view, "OnTransformChanged", None)
            if callable(on_changed):
                on_changed(controller)
        if self._transform_controller_view is not None:
            self._transform_controller_view._sync_control_points_from_controller()
        self.mark_image_layer_dirty()
        self._glpanel.update()

        # Cancel in-progress commands when the model is replaced externally.
        if self._command is None:
            return

        if self._command.status == pyre.CommandStatus.Completed:
            return

        if old is not new or (old is not None and new is not None and old.type != new.type):
            self._command.cancel()

    def subscribe_context_activation(self, glcontext_manager: IGLContextManager):
        glcontext_manager.add_glcontext_added_event_listener(self.create_objects)

    def activate_command(self, previous_command=None):
        command_factory = self._transform_type_to_command_action_map[self.transform_controller.type]  # type: ignore[index]
        self._command = self._command_queue.get()
        if self._command is None:
            # Use GL panel as parent so mouse events and resize use GL viewport coordinates
            gl_w, gl_h = self._glpanel.width(), self._glpanel.height()
            bounds = nornir_imageregistration.Rectangle.CreateFromPointAndArea((0, 0), (gl_w, gl_h))
            self._command = command_factory[ControlPointAction.NONE](parent=self._glpanel,  # type: ignore[index]
                                                                     completed_func=None,
                                                                     commandqueue=self._command_queue,
                                                                     camera=self.camera,
                                                                     bounds=bounds,
                                                                     space=self.space,
                                                                     selected_points=self._selected_points)

        # Ensure we load the next command when this command finishes
        assert self._command is not None
        self._command.add_completed_callback(self.activate_command)
        # Do not print here (e.g. "Activating command: ...") - reduces console noise
        self._command.activate()
        self._update_fixed_layer_hint()

    def on_imageviewmodelmanager_change(self,
                                        name: str,
                                        action: Action,
                                        image: pyre.viewmodels.ImageViewModel):
        """Called when an imageviewmodel is added or removed from the manager"""
        print(
            f'* ImageTransformViewPanel.on_imageviewmodelmanager_change {name} {action.value} self: {self.imagename_space_mapping}')
        if name not in self.imagename_space_mapping:
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
        if self.view_type == ViewType.Composite:
            if self._image_transform_view is None:
                print('\tAdding CompositeTransformView')
                self._image_transform_view = CompositeTransformView(display_space=Space.Target,
                                                                    activate_context=self.glcanvas.activate_context,
                                                                    source_image_name=ViewType.Source.value,
                                                                    target_image_name=ViewType.Target.value,
                                                                    transform_controller=self.transform_controller,
                                                                    gl_funcs=self._glpanel._gl_funcs)  # type: ignore[arg-type]
                self._wire_tile_mesh_repaint(self._image_transform_view)
                # First paintGL can run before sub-view GL meshes exist; dirty so
                # deferred updates refill both overlay FBOs instead of reusing empty ones.
                QTimer.singleShot(50, self._composite_deferred_redraw)
                QTimer.singleShot(150, self._composite_deferred_redraw)
            else:
                # Second add (Target) - drop the source-only retained overlay and redraw.
                self.mark_image_layer_dirty()
                self._glpanel.update()
        else:
            print(f'\tAdding ImageTransformView {name} in space {self.space.value}')
            self._image_transform_view = ImageTransformView(space=self.space,
                                                            activate_context=self.glcanvas.activate_context,
                                                            image_view_model=image,
                                                            transform_controller=self.transform_controller,
                                                            gl_funcs=self._glpanel._gl_funcs)  # type: ignore[arg-type]
            self._wire_tile_mesh_repaint(self._image_transform_view)
            self.mark_image_layer_dirty()
            if self._retained_image_buffer is not None:
                self._retained_image_buffer.invalidate_color()
            print(f'Added image view model {name} to {self.view_type.value} view')

        # Use QTimer to call center_camera after the widget is fully initialized
        QTimer.singleShot(0, self.center_camera)

    def _handle_remove_imageviewmodel_event(self, name: str):
        """Process a remove event from the imageviewmodel manager"""
        self._image_transform_view = None

    def create_objects(self, context: PyQt6.QtGui.QOpenGLContext):
        """create opengl objects when opengl is initialized
        
        Args:
            context: The OpenGL context that was just created and is now current
        """
        if self._image_transform_view is not None:
            self._image_transform_view.create_objects()  # type: ignore[attr-defined]

        if self._transform_controller_view is None:
            self._transform_controller_view = TransformControllerView(transform_controller=self.transform_controller)
            BinarySelectionMapper(self._selected_points,
                                  lambda: getattr(self._transform_controller_view, 'selected'),
                                  lambda value: setattr(self._transform_controller_view, 'selected', value),
                                  point_count=lambda: len(self.transform_controller.points),
                                  repaint=lambda: self._glpanel.update())
            # Activate command directly - no need to defer as context is already active
            self.activate_command()
            if self.view_type == ViewType.Composite:
                QTimer.singleShot(0, self._glpanel.update)

    def on_timer_singleshot(self):
        """Timer callback that reschedules itself - workaround for repeating timer issues"""
        try:
            self.DebugTickCounter += 1
            # Blink only control-point glyphs; reuse the retained texture background.
            self.glcanvas.update()
            # Reschedule the timer
            QTimer.singleShot(100, self.on_timer_singleshot)
        except Exception as e:
            print(f"ERROR in on_timer_singleshot for {self.view_type.value}: {e}")
            import traceback
            traceback.print_exc()

    def on_timer(self):
        """Legacy timer callback - kept for compatibility"""
        self.DebugTickCounter += 1
        self.glcanvas.update()
        return

    def center_camera(self):
        """
        Center the camera at whatever interesting thing this class displays
        """
        if self.camera is None:
            return
        if self._image_transform_view is None or self._image_transform_view.width is None:
            self.camera.lookat = (0, 0)
            self.camera.scale = 1.0
            return

        center = (self._image_transform_view.height / 2.0, self._image_transform_view.width / 2.0)  # type: ignore[operator]
        self.camera.lookat = center

        width_scale = self.width() / self._image_transform_view.width  # type: ignore[operator]
        height_scale = self.height() / self._image_transform_view.height  # type: ignore[operator]

        self.camera.scale = min(width_scale, height_scale)

    def _LabelPreamble(self) -> str:
        return "Source: " if self.space == Space.Source else "Target: "

    def OnImageViewModelChanged(self, space: pyre.Space):
        """Called when the image view model changes"""
        if space != self.space:
            return
        imageviewmodel = self._imageviewmodel_manager[space]
        self.image_transform_view.image_view_model = imageviewmodel  # type: ignore[attr-defined, union-attr]

        self.center_camera()
        self.mark_image_layer_dirty()
        self.glcanvas.update()

    def onTransformChanged(self):
        """Handle transform changes and prefetch visible tile meshes."""
        super().onTransformChanged()
        # Composite sub-views rebuild via their own OnTransformChanged (source is eager
        # full-grid). Avoid a second full mesh rebuild here.
        if isinstance(self._image_transform_view, CompositeTransformView):
            return
        self._update_visible_tile_meshes()

    def onCameraChanged(self):
        """Handle camera changes and prefetch visible tile meshes."""
        self.mark_image_layer_dirty()
        super().onCameraChanged()
        # Composite FBO meshes are not view-dependent (full grid); skip on pan/zoom.
        if isinstance(self._image_transform_view, CompositeTransformView):
            return
        self._update_visible_tile_meshes()

    def _mesh_visible_bounds(self) -> nornir_imageregistration.Rectangle | None:
        """Return the viewport rectangle used for lazy tile mesh builds."""
        if self.camera is None:
            return None
        gl_h, gl_w = self._glpanel.height(), self._glpanel.width()
        if gl_w <= 0 or gl_h <= 0:
            return None
        self.camera.focus(gl_w, gl_h)
        bounding_box = self.camera.VisibleImageBoundingBox
        if self.view_type == ViewType.Composite and self.transform_controller is not None:
            _, bounding_box = resolve_composite_display_draw_params(
                self.camera,
                self.transform_controller,
                (gl_h, gl_w),
            )
        return bounding_box

    def _wire_tile_mesh_repaint(self, view: object) -> None:
        """Connect lazy mesh continuation callbacks to this panel's repaint."""
        repaint = self._glpanel.update
        if hasattr(view, '_repaint_callback'):
            view._repaint_callback = repaint  # type: ignore[attr-defined]
        if isinstance(view, CompositeTransformView):
            view._repaint_callback = repaint
            for sub_view in (view._source_image_view, view._target_image_view):
                if sub_view is not None:
                    sub_view._repaint_callback = repaint

    def _update_visible_tile_meshes(self) -> None:
        """Prefetch tile meshes for the current camera viewport."""
        bounds = self._mesh_visible_bounds()
        if bounds is None or self._image_transform_view is None:
            return
        if isinstance(self._image_transform_view, CompositeTransformView):
            # Full-grid budgeted builds: display-space bounds are not a reliable cull for
            # warped composite source tiles (and incorrectly crop the target layer).
            for sub_view in (
                    self._image_transform_view._source_image_view,
                    self._image_transform_view._target_image_view,
            ):
                if sub_view is not None:
                    sub_view.update_visible_tile_meshes(None, margin_tiles=1)  # type: ignore[attr-defined]
        else:
            self._image_transform_view.update_visible_tile_meshes(bounds, margin_tiles=1)  # type: ignore[union-attr]

    def lookatfixedpoint(self, point, scale):
        """Look at a point specified in Target (control / fixed) space.

        Source and Composite cameras store lookat in Source space, so the point
        is InverseTransformed before applying. Target cameras use the point as-is.
        """
        point = camera_lookat_from_target_space(
            self.transform_controller, point, self.space)

        super(ImageTransformViewPanel, self).lookatfixedpoint(point, scale)  # type: ignore[arg-type]

    def draw(self):
        """Region is [x,y,TextureWidth,TextureHeight] indicating where the image should be drawn on the window"""
        if self.camera is None:
            return

        if self.width() == 0 or self.height() == 0:
            return

        self.camera.focus(self._glpanel.width(), self._glpanel.height())

        self._glpanel.activate_context()

        composite_view_proj = None
        if self._image_transform_view is not None:
            gl_h, gl_w = self._glpanel.height(), self._glpanel.width()
            bounding_box = self.camera.VisibleImageBoundingBox
            view_proj = self.camera.view_proj
            draw_space = self.space
            ratio = self._glpanel.devicePixelRatio()
            overlay_viewport_size = (int(gl_w * ratio), int(gl_h * ratio))
            if self.view_type == ViewType.Composite and self.transform_controller is not None:
                # Use logical GL size for view_proj so mouse pan stays 1:1 with on-screen motion.
                # Physical pixels are only for FBO/viewport fill via overlay_viewport_size.
                view_proj, bounding_box = resolve_composite_display_draw_params(
                    self.camera,
                    self.transform_controller,
                    (gl_h, gl_w),
                )
                composite_view_proj = view_proj
                draw_space = Space.Target

            SetDrawTextureState(self._glpanel._gl_funcs)  # type: ignore[arg-type]

            # Use GL panel size so viewport/FBO match the actual drawing surface.
            # Pass the widget's default FBO so composite overlay draws to the widget (QOpenGLWidget uses an internal FBO, not 0).
            # Pass physical viewport size so composite overlay fills the widget after resize/hi-DPI (resizeGL uses physical pixels).
            default_fbo = self._glpanel.defaultFramebufferObject()
            ov_w, ov_h = overlay_viewport_size
            draw_kwargs: dict[str, object] = {
                "space": draw_space,
                "client_size": (gl_h, gl_w),
                "bounding_box": bounding_box,
                "default_fbo": default_fbo,
                "overlay_viewport_size": overlay_viewport_size,
                "show_mesh_lines": self.show_lines,
                "view_type": self.view_type,
            }
            refill_source = self._image_layer_dirty
            refill_target = self._image_layer_dirty
            if (
                    self.view_type == ViewType.Composite
                    and self.transform_controller is not None
                    and self.transform_controller.freeze_composite_display_during_point_drag()
            ):
                refill_source = True
                refill_target = False
            if isinstance(self._image_transform_view, CompositeTransformView):
                draw_kwargs["refill_source_layer"] = refill_source
                draw_kwargs["refill_target_layer"] = refill_target
                self._image_transform_view.draw(view_proj, **draw_kwargs)
                self._image_layer_dirty = False
            else:
                self._draw_retained_image_layer(
                    view_proj, draw_kwargs, default_fbo, ov_w, ov_h, refill_source)
                self._image_layer_dirty = False

            ClearDrawTextureState(self._glpanel._gl_funcs)  # type: ignore[arg-type]

        if self._transform_controller_view is not None:
            point_scale = (1 / self.camera.scale) * self.control_point_scale
            cp_view_proj = self.camera.view_proj
            if self.view_type == ViewType.Composite and self.transform_controller is not None:
                if composite_view_proj is not None:
                    cp_view_proj = composite_view_proj
                else:
                    gl_h, gl_w = self._glpanel.height(), self._glpanel.width()
                    cp_view_proj, _ = resolve_composite_display_draw_params(
                        self.camera,
                        self.transform_controller,
                        (gl_h, gl_w),
                    )
            self._transform_controller_view.draw(
                cp_view_proj,
                tween=ControlPointMap.draw_tween_for_pyre_space(self.space),
                scale_factor=point_scale,
                blink_phase=self.DebugTickCounter % 2,
                display_point_rows=composite_control_point_draw_rows(
                    self.transform_controller, self.space)
                if self.view_type == ViewType.Composite and self.transform_controller is not None
                else None,
            )
