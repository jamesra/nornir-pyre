"""
Created on Oct 16, 2012

@author: u0490822
"""
from __future__ import annotations
from dataclasses import dataclass
import warnings
import numpy as np

import OpenGL.GL as gl
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QWheelEvent, QMouseEvent

from dependency_injector.wiring import Provide, inject
from dependency_injector.providers import Factory, Dict
import nornir_imageregistration
from nornir_imageregistration import ITransform
from pyre.command_interfaces import ICommand
from pyre.interfaces import ControlPointAction

from pyre.observable import ObservableSet
from pyre.interfaces.action import Action
from pyre.interfaces.managers import ICommandQueue, IGLContextManager
from pyre.interfaces.managers.image_viewmodel_manager import IImageViewModelManager
from pyre.interfaces.managers.transformcontroller_glbuffer_manager import ITransformControllerGLBufferManager, \
    BufferType
import pyre.interfaces.managers.gl_context_manager
from pyre.settings import AppSettings
from pyre.space import Space
from pyre.state import ViewType
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

    _command: ICommand
    _command_queue: CommandQueue
    _transform_controller: TransformController

    _imageviewmodel_manager: IImageViewModelManager = Provide[IContainer.imageviewmodel_manager]
    _glcontext_manager: IGLContextManager = Provide[IContainer.glcontext_manager]
    _transformglbuffer_manager: ITransformControllerGLBufferManager = Provide[IContainer.transform_glbuffermanager]

    _view_type: ViewType
    _transform_type_to_command_action_map: Dict[TransformType, Dict[ControlPointAction, Factory]] = Provide[
        IContainer.action_command_map]

    _imagename_space_mapping: dict[str, Space]  # Maps an image name to a space

    _transform_controller_view: TransformControllerView

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
    def image_transform_view(self) -> IImageTransformView:
        return self._image_transform_view

    @image_transform_view.setter
    def image_transform_view(self, value: IImageTransformView):
        self._image_transform_view = value

    @property
    def max_image_dimension(self):
        return max([self.image_transform_view.width, self.image_transform_view.height])

    @inject
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
        self._command = None
        self._transform_controller_view = None
        self._imagename_space_mapping = imagename_space_mapping
        self._view_type = view_type
        self._transform_controller = transform_controller
        self._space = space
        self._command_queue: ICommandQueue = CommandQueue()

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
        self.timer.start(100)

        self.statusbar.space = self.space

        self._imageviewmodel_manager.add_change_event_listener(self.on_imageviewmodelmanager_change)

        # Use QTimer to call these methods after the widget is fully initialized
        QTimer.singleShot(0, lambda: self.subscribe_context_activation(self._glcontext_manager))

        transform_controller.AddOnModelReplacedEventListener(self._on_transform_model_changed)

    def __del__(self):
        try:
            self._imageviewmodel_manager.remove_change_event_listener(self.on_imageviewmodelmanager_change)
        except ValueError:
            pass

        try:
            self._transform_controller.RemoveOnModelReplacedEventListener(self._on_transform_model_changed)
        except ValueError:
            pass

    def _on_transform_model_changed(self,
                                    controller: TransformController,
                                    old: ITransform | None,
                                    new: ITransform):
        """Called when the model in the transform controller changes.  This is not called when the
        transform is modified, only when the model is replaced"""
        # Cancel the active command
        if self._command is None:
            return

        if old != new:
            self._command.cancel()
        elif old.type != new.type:
            self._command.cancel()

    def subscribe_context_activation(self, glcontext_manager: IGLContextManager):
        glcontext_manager.add_glcontext_added_event_listener(self.create_objects)

    def activate_command(self, previous_command=None):
        command_factory = self._transform_type_to_command_action_map[self.transform_controller.type]
        self._command = self._command_queue.get()
        if self._command is None:
            bounds = nornir_imageregistration.Rectangle.CreateFromPointAndArea((0, 0), (self.width(), self.height()))
            self._command = command_factory[ControlPointAction.NONE](parent=self.glcanvas,
                                                                     completed_func=None,
                                                                     commandqueue=self._command_queue,
                                                                     camera=self.camera,
                                                                     bounds=bounds,
                                                                     space=self.space,
                                                                     selected_points=self._selected_points)

        # Ensure we load the next command when this command finishes
        self._command.add_completed_callback(self.activate_command)
        print(f'Activating command: {self._command}')
        self._command.activate()

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
                                                                    source_image_name=ViewType.Source,
                                                                    target_image_name=ViewType.Target,
                                                                    transform_controller=self.transform_controller)
            else:
                # The CompositeTransformView should exist and be subscribed so this ViewModel should be added by the View
                pass
        else:
            print(f'\tAdding ImageTransformView {name} in space {self.space.value}')
            self._image_transform_view = ImageTransformView(space=self.space,
                                                            activate_context=self.glcanvas.activate_context,
                                                            image_view_model=image,
                                                            transform_controller=self.transform_controller)
            print(f'Added image view model {name} to {self.view_type.value} view')

        # Use QTimer to call center_camera after the widget is fully initialized
        QTimer.singleShot(0, self.center_camera)

    def _handle_remove_imageviewmodel_event(self, name: str):
        """Process a remove event from the imageviewmodel manager"""
        self._image_transform_view = None

    def create_objects(self, context):
        """create opengl objects when opengl is initialized"""
        if self._image_transform_view is not None:
            self._image_transform_view.create_objects()

        if self._transform_controller_view is None:
            self._transform_controller_view = TransformControllerView(transform_controller=self.transform_controller)
            BinarySelectionMapper(self._selected_points,
                                  lambda: getattr(self._transform_controller_view, 'selected'),
                                  lambda value: setattr(self._transform_controller_view, 'selected', value))
            QTimer.singleShot(0, self.activate_command)

    def on_timer(self):
        self.DebugTickCounter += 1
        self.glcanvas.update()
        return

    def center_camera(self):
        """
        Center the camera at whatever interesting thing this class displays
        """
        if self._image_transform_view is None or self._image_transform_view.width is None:
            self.camera.lookat = (0, 0)
            self.camera.scale = 1.0
            return

        center = (self._image_transform_view.height / 2.0, self._image_transform_view.width / 2.0)
        self.camera.lookat = center

        width_scale = self.width() / self._image_transform_view.width
        height_scale = self.height() / self._image_transform_view.height

        self.camera.scale = min(width_scale, height_scale)

    def _LabelPreamble(self) -> str:
        return "Fixed: " if self.FixedSpace else "Warping: "

    def OnImageViewModelChanged(self, space: pyre.Space):
        """Called when the image view model changes"""
        if space == self.space:
            imageviewmodel = self._imageviewmodel_manager[space]
            self.image_transform_view.image_view_model = imageviewmodel
        else:
            return

        self.center_camera()
        self.glcanvas.update()

    def lookatfixedpoint(self, point, scale):
        """specify a point to look at in fixed space"""
        if not self.FixedSpace:
            if not self.ShowWarped:
                if self.transform_controller is not None:
                    point = self.transform_controller.InverseTransform([point]).flat

        super(ImageTransformViewPanel, self).lookatfixedpoint(point, scale)

    def draw(self):
        """Region is [x,y,TextureWidth,TextureHeight] indicating where the image should be drawn on the window"""
        if self.camera is None:
            return

        if self.width() == 0 or self.height() == 0:
            return

        self.camera.focus(self.width(), self.height())

        if self._image_transform_view is not None:
            bounding_box = self.camera.VisibleImageBoundingBox

            SetDrawTextureState()

            # Draw an image if we can
            self._image_transform_view.draw(self.camera.view_proj,
                                            space=self.space,
                                            client_size=(self.height(), self.width()),
                                            bounding_box=bounding_box)

            ClearDrawTextureState()

        if self._transform_controller_view is not None:
            tween = 0 if self.space == pyre.Space.Source else 1
            point_scale = (1 / self.camera.scale) * self.control_point_scale
            self._transform_controller_view.draw(self.camera.view_proj, tween=tween, scale_factor=point_scale)
