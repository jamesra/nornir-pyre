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
from pyre.views import (ClearDrawTextureState, CompositeTransformView, PointView, ImageTransformView,
                        SetDrawTextureState)
from pyre.views.interfaces import IImageTransformView
from pyre.container import IContainer
from nornir_imageregistration.transforms.transform_type import TransformType
from pyre.interfaces.viewtype import ViewType
from pyre.views.transformcontrollerview import BinarySelectionMapper, TransformControllerView
from pyre.transform_edit_policy import fixed_panel_hint_message, rigid_rotation_locked
from pyre.views.composite_display import resolve_composite_display_draw_params


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
        self._show_lines = value

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

    def _update_layer_policy_hints(self) -> None:
        """Show corner hints when transform-edit policy blocks actions in this panel."""
        if getattr(self, '_fixed_layer_hint', None) is not None:
            msg = fixed_panel_hint_message(
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

    def on_resize(self, event: QResizeEvent) -> None:
        """Handle resize and keep the fixed-layer hint anchored."""
        super().on_resize(event)
        if getattr(self, '_fixed_layer_hint', None) is not None and self._fixed_layer_hint.isVisible():
            self._fixed_layer_hint.move(8, 8)
        if getattr(self, '_warped_layer_hint', None) is not None and self._warped_layer_hint.isVisible():
            self._warped_layer_hint.move(8, 8)

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

    def _on_transform_controller_changed(self, controller: TransformController) -> None:
        """Repaint when registration or display overlays change in another STOS view."""
        self._glpanel.update()

    def _on_transform_model_changed(self,
                                    controller: TransformController,
                                    old: ITransform | None,
                                    new: ITransform):
        """Called when the model in the transform controller changes.  This is not called when the
        transform is modified, only when the model is replaced"""
        self._update_fixed_layer_hint()
        # Cancel in-progress commands when the model is replaced externally.
        if self._command is None:
            return

        if self._command.status == pyre.CommandStatus.Completed:
            return

        if old != new or (old is not None and old.type != new.type):
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
                # Force repaint after view's async setup (posted callbacks set source/target views)
                QTimer.singleShot(50, self._glpanel.update)
                QTimer.singleShot(150, self._glpanel.update)
            else:
                # Second add (Target) - request repaint so overlay draws once both views are set
                self._glpanel.update()
        else:
            print(f'\tAdding ImageTransformView {name} in space {self.space.value}')
            self._image_transform_view = ImageTransformView(space=self.space,
                                                            activate_context=self.glcanvas.activate_context,
                                                            image_view_model=image,
                                                            transform_controller=self.transform_controller,
                                                            gl_funcs=self._glpanel._gl_funcs)  # type: ignore[arg-type]
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
        return "Fixed: " if self.FixedSpace else "Warping: "

    def OnImageViewModelChanged(self, space: pyre.Space):
        """Called when the image view model changes"""
        if space != self.space:
            return
        imageviewmodel = self._imageviewmodel_manager[space]
        self.image_transform_view.image_view_model = imageviewmodel  # type: ignore[attr-defined, union-attr]

        self.center_camera()
        self.glcanvas.update()

    def lookatfixedpoint(self, point, scale):
        """specify a point to look at in fixed space"""
        if not self.FixedSpace:
            if not self.ShowWarped:
                if self.transform_controller is not None:
                    point = self.transform_controller.InverseTransform([point]).flat  # type: ignore[arg-type]

        super(ImageTransformViewPanel, self).lookatfixedpoint(point, scale)  # type: ignore[arg-type]

    def draw(self):
        """Region is [x,y,TextureWidth,TextureHeight] indicating where the image should be drawn on the window"""
        if self.camera is None:
            return

        if self.width() == 0 or self.height() == 0:
            return

        self.camera.focus(self._glpanel.width(), self._glpanel.height())

        self._glpanel.activate_context()

        if self._image_transform_view is not None:
            gl_h, gl_w = self._glpanel.height(), self._glpanel.width()
            bounding_box = self.camera.VisibleImageBoundingBox
            view_proj = self.camera.view_proj
            draw_space = self.space
            if self.view_type == ViewType.Composite and self.transform_controller is not None:
                view_proj, bounding_box = resolve_composite_display_draw_params(
                    self.camera,
                    self.transform_controller,
                    (gl_h, gl_w),
                )
                draw_space = Space.Target

            SetDrawTextureState(self._glpanel._gl_funcs)  # type: ignore[arg-type]

            # Use GL panel size so viewport/FBO match the actual drawing surface.
            # Pass the widget's default FBO so composite overlay draws to the widget (QOpenGLWidget uses an internal FBO, not 0).
            # Pass physical viewport size so composite overlay fills the widget after resize/hi-DPI (resizeGL uses physical pixels).
            default_fbo = self._glpanel.defaultFramebufferObject()
            ratio = self._glpanel.devicePixelRatio()
            overlay_viewport_size = (int(gl_w * ratio), int(gl_h * ratio))
            draw_kwargs: dict[str, object] = {
                "space": draw_space,
                "client_size": (gl_h, gl_w),
                "bounding_box": bounding_box,
                "default_fbo": default_fbo,
                "overlay_viewport_size": overlay_viewport_size,
                "show_mesh_lines": self.show_lines,
                "view_type": self.view_type,
            }
            self._image_transform_view.draw(view_proj, **draw_kwargs)

            ClearDrawTextureState(self._glpanel._gl_funcs)  # type: ignore[arg-type]

        if self._transform_controller_view is not None:
            tween = 0 if self.space == pyre.Space.Source else 1
            point_scale = (1 / self.camera.scale) * self.control_point_scale
            self._transform_controller_view.draw(
                self.camera.view_proj,
                tween=tween,
                scale_factor=point_scale,
                blink_phase=self.DebugTickCounter % 2)
