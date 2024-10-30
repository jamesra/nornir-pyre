"""
Created on Oct 16, 2012

@author: u0490822
"""
from __future__ import annotations
from dataclasses import dataclass
import warnings

import OpenGL.GL as gl
import wx

from dependency_injector.wiring import Provide, inject
from dependency_injector.providers import Factory, Dict
import nornir_imageregistration
from nornir_imageregistration import ITransform
from pyre.command_interfaces import ICommand
from pyre.interfaces import ControlPointAction

from pyre.interfaces.action import Action
from pyre.interfaces.managers import ICommandQueue, IGLContextManager
from pyre.interfaces.managers.image_viewmodel_manager import IImageViewModelManager
from pyre.interfaces.managers.transformcontroller_glbuffer_manager import ITransformControllerGLBufferManager, \
    BufferType
import pyre.interfaces.managers.gl_context_manager
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
from pyre.views.transformcontrollerview import TransformControllerView


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
    config = Provide[IContainer.config]

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
    _transform_type_to_command_action_map: Dict[TransformType, ControlPointActionCommandMapType]

    _imagename_space_mapping: dict[str, Space]  # Maps an image name to a space

    _transform_controller_view: TransformControllerView

    @property
    def control_point_scale(self) -> float:
        """Determines how large control points are rendered"""
        return self.config['control_point_search_radius']

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
        return self._config.transform_controller.TransformModel

    @property
    def transform_controller(self) -> TransformController:
        return self._transform_controller

    @property
    def image_transform_view(self) -> IImageTransformView:
        return self._image_transform_view

    @image_transform_view.setter
    def image_transform_view(self, value: IImageTransformView):
        self._image_transform_view = value

        if value is None:
            return
        else:
            assert (isinstance(value, ImageTransformView))

        # (self.width, self.height) = self.canvas.GetSize()

    @property
    def max_image_dimension(self):
        return max([self.image_transform_view.width, self.image_transform_view.height])

    @inject
    def __init__(self,
                 parent: wx.Window,
                 space: Space,
                 view_type: ViewType,
                 transform_controller: TransformController,
                 imagename_space_mapping: dict[str, Space],
                 transform_type_to_command_action_map: dict[TransformType, ControlPointActionCommandMapType] = Provide[
                     IContainer.transform_action_map],
                 **kwargs):
        """
        Constructor
        :param space:
        """
        self._command = None
        self._transform_controller_view = None
        self._imagename_space_mapping = imagename_space_mapping
        self._view_type = view_type
        self._transform_controller = transform_controller
        self._space = space
        self._command_queue: ICommandQueue = CommandQueue()
        self._transform_type_to_command_action_map = pyre.commands.container_overrides.action_command_map

        super().__init__(parent=parent,
                         transform_controller=transform_controller,
                         **kwargs)

        # self._config.imageviewmodel_manager.add_change_event_listener(self.OnImageViewModelChanged)

        # self.schedule = clock.schedule_interval(func = self.update, interval = 1 / 2.)
        self.timer = wx.Timer(self._glpanel)
        self.glcanvas.Bind(wx.EVT_TIMER, self.on_timer)

        # wx.EVT_TIMER(self, -1, self.on_timer)

        self.ShowWarped = False

        self.glFunc = gl.GL_FUNC_ADD

        self.LastDrawnBoundingBox = None

        # self._bind_mouse_events()
        # self.glcanvas.Bind(wx.EVT_KEY_DOWN, self.on_key_press)

        self._image_transform_view = None
        # self._image_transform_view = ImageTransformView(space=self.space,
        #                                                 activate_context=self.activate_context,
        #                                                 image_view_model=None,
        #                                                 transform_controller=state.currentStosConfig.transform_controller)

        self.DebugTickCounter = 0
        self.timer.Start(100)

        self.statusbar.space = self.space

        self._imageviewmodel_manager.add_change_event_listener(self.on_imageviewmodelmanager_change)

        # wx.CallAfter(self.create_objects)
        wx.CallAfter(self.subscribe_context_activation, self._glcontext_manager)

        transform_controller.AddOnModelReplacedEventListener(self._on_transform_model_changed)

    def _on_transform_model_changed(self,
                                    controller: TransformController,
                                    old: ITransform | None,
                                    new: ITransform):
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
            bounds = nornir_imageregistration.Rectangle.CreateFromPointAndArea((0, 0), (self.width, self.height))
            self._command = command_factory[ControlPointAction.NONE](parent=self.glcanvas,
                                                                     completed_func=None,
                                                                     commandqueue=self._command_queue,
                                                                     camera=self.camera,
                                                                     bounds=bounds,
                                                                     space=self.space,
                                                                     setselection=self._transform_controller_view.set_selected_by_index)

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
        # self._image_transform_view.image_view_model = image
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

        self.center_camera()

    def _handle_remove_imageviewmodel_event(self, name: str):
        """Process a remove event from the imageviewmodel manager"""
        self._image_transform_view = None

    def create_objects(self, context):
        """create opengl objects when opengl is initialized"""
        # self.activate_context() Context should be set by parent class
        # load_point_textures() Textures should be loaded already by registration with context manager

        if self._image_transform_view is not None:
            self._image_transform_view.create_objects()

        if self._transform_controller_view is None:
            self._transform_controller_view = TransformControllerView(transform_controller=self.transform_controller)
            wx.CallAfter(self.activate_command)

    def on_timer(self, e):
        #        DebugStr = '%d' % self.DebugTickCounter
        #        DebugStr = DebugStr + '\b' * len(DebugStr)
        #        print DebugStr
        # print(f'{self.view_type}')
        self.DebugTickCounter += 1
        self.glcanvas.Refresh()
        return

    def _LabelPreamble(self) -> str:
        return "Fixed: " if self.FixedSpace else "Warping: "

    def OnImageViewModelChanged(self, space: pyre.Space):
        """Called when the image view model changes"""
        if space == self.space:
            imageviewmodel = self._imageviewmodel_manager[space]
            self.image_transform_view.image_view_model = imageviewmodel
        else:
            return

        #
        # if self.composite:
        #     self.UpdateRawImageWindow()
        # elif self.FixedSpace and space == pyre.Space.Source:
        #     self.UpdateRawImageWindow()
        #     if self.image_transform_view.image_view_model is not None:
        #         self.TopLevelParent.Label = self._LabelPreamble() + os.path.basename(
        #             self.image_transform_view.image_view_model.ImageFilename)
        #
        # # self.lookatfixedpoint((0,0), 1.0)

        self.center_camera()
        self.glcanvas.Refresh()

    # def UpdateRawImageWindow(self):
    #     """Update the control that displays images"""
    #     if self.composite:
    #         if not (
    #                 state.currentStosConfig.FixedImageViewModel is None or state.currentStosConfig.WarpedImageViewModel is None):
    #             self.image_transform_view = CompositeTransformView(self._glcontextmanager,
    #                                                                  state.currentStosConfig.FixedImageViewModel,
    #                                                                  state.currentStosConfig.WarpedImageViewModel,
    #                                                                  state.currentStosConfig.transform_controller)
    #     elif self.space == pyre.Space.Target:
    #         self.image_transform_view = ImageTransformView(space=self.space,
    #                                                          glcontexmanager=self._glcontextmanager,
    #                                                          ImageViewModel=state.currentStosConfig.WarpedImageViewModel,
    #                                                          transform_controller=state.currentStosConfig.transform_controller)
    #     else:
    #         self.image_transform_view = ImageTransformView(space=self.space,
    #                                                          glcontexmanager=self._glcontextmanager,
    #                                                          ImageViewModel=state.currentStosConfig.FixedImageViewModel,
    #                                                          transform_controller=state.currentStosConfig.transform_controller)

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

        if self.width == 0 or self.height == 0:
            return

        self.camera.focus(self.width, self.height)

        if self._image_transform_view is not None:
            bounding_box = self.camera.VisibleImageBoundingBox

            SetDrawTextureState()

            # Draw an image if we can
            self._image_transform_view.draw(self.camera.view_proj,
                                            space=self.space,
                                            client_size=(self.height, self.width),
                                            bounding_box=bounding_box)

            ClearDrawTextureState()

        # FixedSpacePoints = self.FixedSpace
        # FixedSpaceLines = FixedSpacePoints
        # if self.composite:
        #     FixedSpacePoints = False
        #     FixedSpaceLines = True
        # else:
        #     # This looks backwards, and it is.  The transform object itself refers to warped and fixed space.  Depending on how warped is interpreted it means
        #     # the points that are warped or the points that have been warped.  It needs to be refactored to make the names unabiguous
        #     FixedSpacePoints = self.FixedSpace or self.ShowWarped
        #     FixedSpaceLines = self.FixedSpace or self.ShowWarped
        #
        # if self.show_lines:
        #     self._ImageTransformView.draw_lines(draw_in_fixed_space=FixedSpaceLines)

        # self._ImageTransformView.draw(view_proj=self.camera.view_proj, space=self.space)
        if self._transform_controller_view is not None:
            tween = 0 if self.space == pyre.Space.Source else 1
            # print(f"Drawing {self.space.value} control points tween: {tween}")
            point_scale = (1 / self.camera.scale) * self.control_point_scale
            self._transform_controller_view.draw(self.camera.view_proj, tween=tween, scale_factor=point_scale)

        # pointScale = (bounding_box[3] * bounding_box[2]) / (self.height * self.width)
        # pointScale = self.camera.scale / self.height
        # self._ImageTransformView.draw_points(SelectedIndex=self.HighlightedPointIndex, bounding_box=bounding_box,
        #                                     FixedSpace=FixedSpacePoints, ScaleFactor=pointScale)

    #       graphics.draw(2, gl.GL_LINES, ('v2i', (0, 0, 0, 10)))
    #       graphics.draw(2, gl.GL_LINES, ('v2i', (0, 0, 100, 0)))

    # if not self.LastMousePosition is None and len(self.LastMousePosition) > 0:

    #            fontsize = 16 * (self.camera.scale / self.height)
    #            labelx, labely = self.ImageCoordsForMouse(0, 0)
    #            l = text.Label(text = mousePosStr, x = labelx, y = labely,
    #                            width = fontsize * len(mousePosStr),
    #                            anchor_y = 'bottom',
    #                            font_size = fontsize,
    #                            dpi = 300,
    #                            font_name = 'Times New Roman')
    #            l.draw()
    #
    # def on_mouse_motion(self, x, y, dx, dy):
    #     self.LastMousePosition = [y, x]
    #
    #     self.statusBar.update_status_bar(self.LastMousePosition, in_target_space=self.FixedSpace)
    #
    # def on_mouse_scroll(self, e):
    #
    #     if self.camera is None:
    #         return
    #
    #     scroll_y = e.GetWheelRotation() / 120.0
    #
    #     if e.CmdDown() and e.AltDown() and isinstance(self.transform_controller.TransformModel,
    #                                                   nornir_imageregistration.ITransformRelativeScaling):
    #         scale_delta = (1.0 + (-scroll_y / 50.0))
    #         self.transform_controller.TransformModel.ScaleWarped(scale_delta)
    #     elif e.CmdDown():  # We rotate when command is down
    #         angle = float(abs(scroll_y) * 2) ** 2.0
    #         if e.ShiftDown():
    #             angle = float(abs(scroll_y) / 2) ** 2.0
    #
    #         rangle = (angle / 180.0) * 3.14159
    #         if scroll_y < 0:
    #             rangle = -rangle
    #
    #         # print "Angle: " + str(angle)
    #         try:
    #             self.transform_controller.Rotate(rangle, np.array(
    #                 pyre.state.currentStosConfig.WarpedImageViewModel.Image.shape) / 2.0)
    #         except NotImplementedError:
    #             print("Current transform does not support rotation")
    #             pass
    #
    #         # if isinstance(self._transform_controller.TransformModel, nornir_imageregistration.ITransformTargetRotation):
    #         #     self._transform_controller.TransformModel.RotateTargetPoints(-rangle,
    #         #                                       (state.currentStosConfig.FixedImageMaskViewModel.RawImageSize[0] / 2.0,
    #         #                                        state.currentStosConfig.FixedImageMaskViewModel.RawImageSize[1] / 2.0))
    #         # elif isinstance(self._transform_controller.TransformModel, nornir_imageregistration.ITransformSourceRotation):
    #         #     self._transform_controller.TransformModel.RotateSourcePoints(rangle,
    #         #                                           (state.currentStosConfig.WarpedImageViewModel.RawImageSize[
    #         #                                                0] / 2.0,
    #         #                                            state.currentStosConfig.WarpedImageViewModel.RawImageSize[
    #         #                                                1] / 2.0))
    #
    #     elif self.image_transform_view is not None:
    #         zdelta = (1 + (-scroll_y / 20))
    #
    #         new_scale = self.camera.scale * zdelta
    #         max_image_dimension_value = self.max_image_dimension
    #         if self.transform_controller.width is not None:
    #             max_transform_dimension = max(self.transform_controller.width, self.transform_controller.height)
    #             max_image_dimension_value = max(max_image_dimension_value, max_transform_dimension)
    #
    #         if new_scale > max_image_dimension_value * 2.0:
    #             new_scale = max_image_dimension_value * 2.0
    #
    #         if new_scale < 0.5:
    #             new_scale = 0.5
    #
    #         self.camera.scale = new_scale
    #
    #         scrolling_at = e.X, e.Y
    #         world_coordinates = np.array(self.camera.ImageCoordsForMouse(x=e.X, y=e.Y))
    #
    #         # self.camera.lookat = scrolling_at_position[:2]
    #         print(f'Scrolling at {scrolling_at} position {world_coordinates[:2]}')
    #
    #     self.statusbar.update_status_bar(self.LastMousePosition, in_target_space=self.FixedSpace)

    #
    # def on_mouse_release(self, e):
    #     self.SelectedPointIndex = None
    #
    # def on_mouse_press(self, e):
    #     (y, x) = self.GetCorrectedMousePosition(e)
    #     ImageY, ImageX = self.camera.ImageCoordsForMouse(y, x)
    #
    #     if ImageX is None or ImageY is None:
    #         return
    #
    #     self.LastMousePosition = (y, x)
    #
    #     if self.transform_controller is None:
    #         return
    #
    #     if e.MiddleIsDown():
    #         self.center_camera()
    #
    #     if not isinstance(self.transform_controller.TransformModel, nornir_imageregistration.transforms.IControlPoints):
    #         # The remaining functions require control points
    #         return
    #
    #     if e.ShiftDown():
    #         if e.LeftDown() and self.SelectedPointIndex is None:
    #             self.SelectedPointIndex = self.transform_controller.TryAddPoint(ImageX, ImageY,
    #                                                                             space=self.space)
    #             if e.AltDown():
    #                 self.transform_controller.AutoAlignPoints(self.SelectedPointIndex)
    #
    #             history.SaveState(self.transform_controller.SetPoints, self.transform_controller.points)
    #         elif e.RightDown():
    #             self.transform_controller.TryDeletePoint(ImageX, ImageY, self.SelectionMaxDistance,
    #                                                      space=self.space)
    #             if self.SelectedPointIndex is not None:
    #                 if self.SelectedPointIndex > self.transform_controller.NumPoints:
    #                     self.SelectedPointIndex = self.transform_controller.NumPoints - 1
    #
    #             history.SaveState(self.transform_controller.SetPoints, self.transform_controller.points)
    #
    #     elif e.LeftDown():
    #         if e.AltDown() and not self.HighlightedPointIndex is None:
    #             self.transform_controller.SetPoint(self.HighlightedPointIndex, ImageX, ImageY,
    #                                                space=self.space)
    #             history.SaveState(self.transform_controller.SetPoints, self.transform_controller.points)
    #         else:
    #             distance, index = (None, None)
    #             if not self.composite:
    #                 distance, index = self.transform_controller.NearestPoint((ImageY, ImageX),
    #                                                                          space=self.space)
    #             else:
    #                 distance, index = self.transform_controller.NearestPoint((ImageY, ImageX), space=self.space)
    #
    #             if distance is None:
    #                 return
    #
    #             print("d: " + str(distance) + " to p# " + str(index) + " max d: " + str(self.SelectionMaxDistance))
    #             self.SelectedPointIndex = index if distance < self.SelectionMaxDistance else None
    #
    # def on_mouse_drag(self, e):
    #
    #     (y, x) = self.GetCorrectedMousePosition(e)
    #
    #     if self.LastMousePosition is None:
    #         self.LastMousePosition = (y, x)
    #         return
    #
    #     dx = x - self.LastMousePosition[nornir_imageregistration.iPoint.X]
    #     dy = (y - self.LastMousePosition[nornir_imageregistration.iPoint.Y])
    #
    #     self.LastMousePosition = (y, x)
    #
    #     ImageY, ImageX = self.camera.ImageCoordsForMouse(y, x)
    #     if ImageX is None:
    #         return
    #
    #     ImageDX = (float(dx) / self.width) * self.camera.visible_world_width
    #     ImageDY = (float(dy) / self.height) * self.camera.visible_world_height
    #
    #     if e.RightIsDown():
    #         self.camera.lookat = (self.camera.y - ImageDY, self.camera.x - ImageDX)
    #
    #     if e.LeftIsDown():
    #         if e.CmdDown():
    #             # Translate all points
    #             self.transform_controller.TranslateFixed((ImageDY, ImageDX))
    #         else:
    #             # Create a point or drag a point
    #             if self.SelectedPointIndex is not None:
    #                 self.SelectedPointIndex = self.transform_controller.MovePoint(self.SelectedPointIndex, ImageDX,
    #                                                                               ImageDY, space=self.space)
    #             elif e.ShiftDown():  # The shift key is selected and we do not have a last point dragged
    #                 return
    #             else:
    #                 # find nearest point
    #                 self.SelectedPointIndex = self.transform_controller.TryDrag(ImageX, ImageY, ImageDX, ImageDY,
    #                                                                             self.SelectionMaxDistance,
    #                                                                             space=self.space)
    #
    #     self.statusbar.update_status_bar(self.LastMousePosition, in_target_space=self.FixedSpace)
