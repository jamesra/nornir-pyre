"""
Created on Oct 16, 2012

@author: u0490822
"""

import math
import time
import os
import numpy as np
import nornir_imageregistration
import OpenGL.GL as gl
import warnings
# import pyglet
# from pyglet import *

import pyre.state
from dataclasses import dataclass
from pyre.space import Space
from pyre import history, state
import wx

from pyre.state import Action

from . import imagetransformpanelbase
from pyre.ui import Camera
from pyre.viewmodels import TransformController
from pyre.views import (CompositeTransformView, ImageTransformView,
                        SetDrawTextureState, ClearDrawTextureState,
                        ControlPointView)
from pyre.state import IImageViewModelManager, ITransformControllerGLBufferManager, BufferType


@dataclass
class ImageTransformPanelConfig:
    glcontext_manager: pyre.state.IGLContextManager
    transform_controller: TransformController
    transformglbuffer_manager: ITransformControllerGLBufferManager
    imageviewmodel_manager: IImageViewModelManager
    imagenames: set[str]  # Names in the imageviewmodel_manager that this panel should listen to


class ImageTransformViewPanel(imagetransformpanelbase.ImageTransformPanelBase):
    """
    The main editing control for a transform.
    """
    _CurrentDragPoint: int | None = None
    _HighlightedPointIndex: int | None = 0
    _space: pyre.Space = pyre.Space.Source
    _ImageTransformView: ImageTransformView | None = None  # The transformed image
    _controlpoint_view: ControlPointView | None = None  # Control points for the transformed image, if they exist
    _show_lines: bool = False
    _config: ImageTransformPanelConfig

    @property
    def config(self) -> ImageTransformPanelConfig:
        return self._config

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
    def composite(self) -> bool:
        return self._space == pyre.Space.Composite

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
    def HighlightedPointIndex(self) -> int:
        return ImageTransformViewPanel._HighlightedPointIndex

    @property
    def TransformController(self) -> TransformController:
        return state.currentStosConfig.TransformController

    @property
    def ImageGridTransformView(self) -> ImageTransformView:
        return self._ImageTransformView

    @ImageGridTransformView.setter
    def ImageGridTransformView(self, value: ImageTransformView):

        self._ImageTransformView = value

        if value is None:
            return
        else:
            assert (isinstance(value, ImageTransformView))

        (self.width, self.height) = self.canvas.GetSize()

    @property
    def SelectionMaxDistance(self) -> float:
        selectionMaxDistance = (float(self.camera.ViewHeight) / float(self.height)) * 20.0
        if selectionMaxDistance < 16:
            selectionMaxDistance = 16

        return selectionMaxDistance

    def __init__(self,
                 parent: wx.Window,
                 space: Space,
                 config: ImageTransformPanelConfig,
                 **kwargs):
        """
        Constructor
        :param composite: true if we are showing a composite image, if false we are using FixedSpace to determine the image we are showing
        :param FixedSpace: true if we are showing the fixed space image, if false we are showing the warped image
        """
        self._config = config
        self._space = space

        super().__init__(parent=parent,
                         glcontextmanager=config.glcontext_manager,
                         **kwargs)

        state.currentStosConfig.AddOnTransformControllerChangeEventListener(self.OnTransformViewModelChanged)
        state.currentStosConfig.AddOnImageViewModelChangeEventListener(self.OnImageViewModelChanged)

        # self.schedule = clock.schedule_interval(func = self.update, interval = 1 / 2.)
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_timer)

        (self.width, self.height) = self.canvas.GetSize()

        # wx.EVT_TIMER(self, -1, self.on_timer)

        self.LastMousePosition = None

        self.ShowWarped = False

        self.glFunc = gl.GL_FUNC_ADD

        self.LastDrawnBoundingBox = None

        self._bind_mouse_events()

        self.Bind(wx.EVT_KEY_DOWN, self.on_key_press)
        self.canvas.Bind(wx.EVT_KEY_DOWN, self.on_key_press)
        self.canvas.Bind(wx.EVT_SIZE, self.on_resize)

        self.ImageGridTransformView = ImageTransformView(space=self.space,
                                                         activate_context=self.activate_context,
                                                         ImageViewModel=None,
                                                         transform_controller=state.currentStosConfig.TransformController)

        self.DebugTickCounter = 0
        self.timer.Start(100)

        config.imageviewmodel_manager.add_change_event_listener(self.on_imageviewmodelmanager_change)

    def on_imageviewmodelmanager_change(self,
                                        manager: IImageViewModelManager,
                                        name: str,
                                        action: Action,
                                        image: pyre.viewmodels.ImageViewModel):
        """Called when an imageviewmodel is added or removed from the manager"""
        if name not in self.config.imagenames:
            return  # Not of interest to our class

        if action == Action.ADD:
            self._handle_add_imageviewmodel_event(name, image)
        elif action == Action.REMOVE:
            self._handle_remove_imageviewmodel_event(name)
        else:
            raise NotImplementedError()

    def _handle_add_imageviewmodel_event(self, name: str, image: pyre.viewmodels.ImageViewModel):
        """Process an add event from the imageviewmodel manager"""
        self.ImageGridTransformView = ImageTransformView(space=self.space,
                                                         glcontexmanager=self.config.glcontext_manager,
                                                         ImageViewModel=state.currentStosConfig.WarpedImageViewModel,
                                                         transform_controller=state.currentStosConfig.TransformController)

    def _handle_remove_imageviewmodel_event(self, name: str):
        """Process a remove event from the imageviewmodel manager"""
        self.ImageGridTransformView = None

    def create_objects(self):
        """create opengl objects when opengl is initialized"""
        super().create_objects()
        # self.activate_context() Context should be set by parent class
        # load_point_textures() Textures should be loaded already by registration with context manager

        if self._ImageTransformView is not None:
            self._ImageTransformView.create_objects()

        glcontrolpointbuffer = self.config.transformglbuffer_manager.get_glbuffer(
            self.config.transform_controller,
            BufferType.ControlPoint)
        glselectionbuffer = self.config.transformglbuffer_manager.get_glbuffer(
            self.config.transform_controller,
            BufferType.Selection)
        self._controlpoint_view = ControlPointView(points=glcontrolpointbuffer,
                                                   texture_indicies=glselectionbuffer,
                                                   texture=pyre.resources.pointtextures.PointArray)

    def _bind_mouse_events(self):
        self.canvas.Bind(wx.EVT_MOUSEWHEEL, self.on_mouse_scroll)
        self.canvas.Bind(wx.EVT_LEFT_DOWN, self.on_mouse_press)
        self.canvas.Bind(wx.EVT_MIDDLE_DOWN, self.on_mouse_press)
        self.canvas.Bind(wx.EVT_RIGHT_DOWN, self.on_mouse_press)
        self.canvas.Bind(wx.EVT_MOTION, self.on_mouse_drag)
        self.canvas.Bind(wx.EVT_LEFT_UP, self.on_mouse_release)

    def on_timer(self, e):
        #        DebugStr = '%d' % self.DebugTickCounter
        #        DebugStr = DebugStr + '\b' * len(DebugStr)
        #        print DebugStr
        self.DebugTickCounter += 1
        self.canvas.Refresh()
        return

    def OnTransformViewModelChanged(self, transform_controller: TransformController):
        if self.ImageGridTransformView is not None:
            self.ImageGridTransformView._transform_controller = transform_controller

        self.canvas.Refresh()

    def _LabelPreamble(self):
        return "Fixed: " if self.FixedSpace else "Warping: "

    def OnImageViewModelChanged(self, space: pyre.Space):
        """Called when the image view model changes"""
        if space == self.space:
            imageviewmodel = self.config.imageviewmodel_manager[space]
            self.ImageGridTransformView.image_view_model = imageviewmodel
        else:
            return

        #
        # if self.composite:
        #     self.UpdateRawImageWindow()
        # elif self.FixedSpace and space == pyre.Space.Source:
        #     self.UpdateRawImageWindow()
        #     if self.ImageGridTransformView.image_view_model is not None:
        #         self.TopLevelParent.Label = self._LabelPreamble() + os.path.basename(
        #             self.ImageGridTransformView.image_view_model.ImageFilename)
        #
        # # self.lookatfixedpoint((0,0), 1.0)

        self.center_camera()
        self.canvas.Refresh()

    # def UpdateRawImageWindow(self):
    #     """Update the control that displays images"""
    #     if self.composite:
    #         if not (
    #                 state.currentStosConfig.FixedImageViewModel is None or state.currentStosConfig.WarpedImageViewModel is None):
    #             self.ImageGridTransformView = CompositeTransformView(self._glcontextmanager,
    #                                                                  state.currentStosConfig.FixedImageViewModel,
    #                                                                  state.currentStosConfig.WarpedImageViewModel,
    #                                                                  state.currentStosConfig.TransformController)
    #     elif self.space == pyre.Space.Target:
    #         self.ImageGridTransformView = ImageTransformView(space=self.space,
    #                                                          glcontexmanager=self._glcontextmanager,
    #                                                          ImageViewModel=state.currentStosConfig.WarpedImageViewModel,
    #                                                          transform_controller=state.currentStosConfig.TransformController)
    #     else:
    #         self.ImageGridTransformView = ImageTransformView(space=self.space,
    #                                                          glcontexmanager=self._glcontextmanager,
    #                                                          ImageViewModel=state.currentStosConfig.FixedImageViewModel,
    #                                                          transform_controller=state.currentStosConfig.TransformController)

    def NextGLFunction(self):
        if self.glFunc == gl.GL_FUNC_ADD:
            self.glFunc = gl.GL_FUNC_SUBTRACT
        else:
            self.glFunc = gl.GL_FUNC_ADD

    def on_key_press(self, e):
        keycode = e.GetKeyCode()

        symbol = ''
        try:
            KeyChar = '%c' % keycode
            symbol = KeyChar.lower()
        except:
            pass

        if keycode == wx.WXK_TAB:
            try:
                if self.composite:
                    self.NextGLFunction()
                else:
                    self.ShowWarped = not self.ShowWarped
            except:
                pass

        elif (keycode == wx.WXK_LEFT or \
              keycode == wx.WXK_RIGHT or \
              keycode == wx.WXK_UP or \
              keycode == wx.WXK_DOWN) and not self.HighlightedPointIndex is None:

            # Users can nudge points with the arrow keys.  Holding shift steps five pixels, holding Ctrl shifts 25.  Holding both steps 125
            multiplier = 1
            print(str(multiplier))
            if e.ShiftDown():
                multiplier *= 5
                print(str(multiplier))
            if e.ControlDown():
                multiplier *= 25
                print(str(multiplier))

            if keycode == wx.WXK_LEFT:
                delta = [0, -1]
            elif keycode == wx.WXK_RIGHT:
                delta = [0, 1]
            elif keycode == wx.WXK_UP:
                delta = [1, 0]
            elif keycode == wx.WXK_DOWN:
                delta = [-1, 0]

            delta[0] *= multiplier
            delta[1] *= multiplier

            print(str(multiplier))
            self.TransformController.MovePoint(self.HighlightedPointIndex, delta[1], delta[0],
                                               FixedSpace=self.FixedSpace)

        elif symbol == 'a':  # "A" Character
            ImageDX = 0.1 * self.camera.ViewWidth
            self.camera.x = self.camera.x + ImageDX
        elif symbol == 'd':  # "D" Character
            ImageDX = -0.1 * self.camera.ViewWidth
            self.camera.x = self.camera.x + ImageDX
        elif symbol == 'w':  # "W" Character
            ImageDY = -0.1 * self.camera.ViewHeight
            self.camera.y = self.camera.y + ImageDY
        elif symbol == 's':  # "S" Character
            ImageDY = 0.1 * self.camera.ViewHeight
            self.camera.y = self.camera.y + ImageDY

        elif keycode == wx.WXK_PAGEUP:
            self.camera.scale = self.scale * 0.9
        elif keycode == wx.WXK_PAGEDOWN:
            self.camera.scale *= 1.1
        elif keycode == wx.WXK_SPACE:

            # If SHIFT is held down, align everything.  Otherwise align the selected point
            if not e.ShiftDown() and not self.HighlightedPointIndex is None:
                self.SelectedPointIndex = self.TransformController.AutoAlignPoints(self.HighlightedPointIndex)

            elif e.ShiftDown():
                self.TransformController.AutoAlignPoints(range(0, self.TransformController.NumPoints))

            history.SaveState(self.TransformController.SetPoints, self.TransformController.points)
        elif symbol == 'l':
            self.show_lines = not self.show_lines
        elif keycode == wx.WXK_F1:
            self._ImageTransformView.Debug = not self._ImageTransformView.Debug
        elif symbol == 'm':
            LookAt = [self.camera.y, self.camera.x]

            # if not self.FixedSpace and self.ShowWarped:
            #    LookAt = self._transform_controller.transform([LookAt])
            #    LookAt = LookAt[0]

            state.currentStosConfig.WindowsLookAtFixedPoint(LookAt, self.camera.scale)
            # pyre.SyncWindows(LookAt, self.camera.scale)

        elif symbol == 'z' and e.CmdDown():
            history.Undo()
        elif symbol == 'x' and e.CmdDown():
            history.Redo()
        elif symbol == 'f':
            self.TransformController.FlipWarped()
            history.SaveState(self.TransformController.FlipWarped)

    def lookatfixedpoint(self, point, scale):
        """specify a point to look at in fixed space"""

        if not self.FixedSpace:
            if not self.ShowWarped:
                if not self.TransformController is None:
                    point = self.TransformController.InverseTransform([point]).flat

        super(ImageTransformViewPanel, self).lookatfixedpoint(point, scale)

    def center_camera(self):
        """Center the camera at whatever interesting thing this class displays
        """

        view = self.ImageGridTransformView

        #         try:
        #             if not view is None:

        # self.camera = camera.Camera((view.width / 2.0, view.height / 2.0), max([view.width / 2.0, view.height / 2.0]))
        if isinstance(self.TransformController.TransformModel, nornir_imageregistration.IDiscreteTransform):
            fixed_bounding_box = self.TransformController.TransformModel.FixedBoundingBox
            #         except TypeError:
            #             print("Type error creating camera for ImageGridTransformView %s" % str(view))
            #             self.camera = None
            #             pass
        elif self.ImageGridTransformView is not None and self.ImageGridTransformView.width is not None:
            fixed_bounding_box = nornir_imageregistration.Rectangle.CreateFromPointAndArea((0, 0), (
                self.ImageGridTransformView.height, self.ImageGridTransformView.width))
        else:
            return
            # raise NotImplementedError("Not done")

        self.camera.lookat = fixed_bounding_box.Center
        self.camera.scale = fixed_bounding_box.Width

        return

    def draw_objects(self):
        """Region is [x,y,TextureWidth,TextureHeight] indicating where the image should be drawn on the window"""

        if self._ImageTransformView is None or self.camera is None:
            return

        self.camera.focus(self.width, self.height)

        BoundingBox = self.camera.VisibleImageBoundingBox

        SetDrawTextureState()

        # Draw an image if we can
        if not self.composite:
            self._ImageTransformView.draw(self.camera.view_proj,
                                          bounding_box=BoundingBox,
                                          space=self.space,
                                          glFunc=gl.GL_FUNC_ADD)
        else:
            self._ImageTransformView.draw(self.camera.view_proj,
                                          bounding_box=BoundingBox,
                                          space=self.space,
                                          glFunc=self.glFunc)

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

        tween = 0 if self.space == pyre.Space.Source else 1
        point_scale = (self.camera.scale / min(self.height, self.width)) * 10
        self._controlpoint_view.draw(self.camera.view_proj, tween=tween, scale_factor=point_scale)

        # pointScale = (BoundingBox[3] * BoundingBox[2]) / (self.height * self.width)
        # pointScale = self.camera.scale / self.height
        # self._ImageTransformView.draw_points(SelectedIndex=self.HighlightedPointIndex, BoundingBox=BoundingBox,
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

    def on_mouse_motion(self, x, y, dx, dy):
        self.LastMousePosition = [y, x]

        self.statusBar.update_status_bar(self.LastMousePosition, in_target_space=self.FixedSpace)

    def on_mouse_scroll(self, e):

        if self.camera is None:
            return

        scroll_y = e.GetWheelRotation() / 120.0

        if e.CmdDown() and e.AltDown() and isinstance(self.TransformController.TransformModel,
                                                      nornir_imageregistration.ITransformRelativeScaling):
            scale_delta = (1.0 + (-scroll_y / 50.0))
            self.TransformController.TransformModel.ScaleWarped(scale_delta)
        elif e.CmdDown():  # We rotate when command is down
            angle = float(abs(scroll_y) * 2) ** 2.0
            if e.ShiftDown():
                angle = float(abs(scroll_y) / 2) ** 2.0

            rangle = (angle / 180.0) * 3.14159
            if scroll_y < 0:
                rangle = -rangle

            # print "Angle: " + str(angle)
            try:
                self.TransformController.Rotate(rangle, np.array(
                    pyre.state.currentStosConfig.WarpedImageViewModel.Image.shape) / 2.0)
            except NotImplementedError:
                print("Current transform does not support rotation")
                pass

            # if isinstance(self._transform_controller.TransformModel, nornir_imageregistration.ITransformTargetRotation):
            #     self._transform_controller.TransformModel.RotateTargetPoints(-rangle,
            #                                       (state.currentStosConfig.FixedImageMaskViewModel.RawImageSize[0] / 2.0,
            #                                        state.currentStosConfig.FixedImageMaskViewModel.RawImageSize[1] / 2.0))
            # elif isinstance(self._transform_controller.TransformModel, nornir_imageregistration.ITransformSourceRotation):
            #     self._transform_controller.TransformModel.RotateSourcePoints(rangle,
            #                                           (state.currentStosConfig.WarpedImageViewModel.RawImageSize[
            #                                                0] / 2.0,
            #                                            state.currentStosConfig.WarpedImageViewModel.RawImageSize[
            #                                                1] / 2.0))

        else:
            zdelta = (1 + (-scroll_y / 20))

            new_scale = self.camera.scale * zdelta
            max_image_dimension_value = self.max_image_dimension
            if self.TransformController.width is not None:
                max_transform_dimension = max(self.TransformController.width, self.TransformController.height)
                max_image_dimension_value = max(max_image_dimension_value, max_transform_dimension)

            if new_scale > max_image_dimension_value * 2.0:
                new_scale = max_image_dimension_value * 2.0

            if new_scale < 0.5:
                new_scale = 0.5

            self.camera.scale = new_scale

            scrolling_at = e.X, e.Y
            world_coordinates = np.array(self.camera.ImageCoordsForMouse(x=e.X, y=e.Y))

            # self.camera.lookat = scrolling_at_position[:2]
            print(f'Scrolling at {scrolling_at} position {world_coordinates[:2]}')

        self.statusBar.update_status_bar(self.LastMousePosition, in_target_space=self.FixedSpace)

    @property
    def max_image_dimension(self):
        return max([self.ImageGridTransformView.width, self.ImageGridTransformView.height])

    def on_mouse_release(self, e):
        self.SelectedPointIndex = None

    def on_mouse_press(self, e):
        (y, x) = self.GetCorrectedMousePosition(e)
        ImageY, ImageX = self.camera.ImageCoordsForMouse(y, x)

        if ImageX is None or ImageY is None:
            return

        self.LastMousePosition = (y, x)

        if self.TransformController is None:
            return

        if e.MiddleIsDown():
            self.center_camera()

        if not isinstance(self.TransformController.TransformModel, nornir_imageregistration.transforms.IControlPoints):
            # The remaining functions require control points
            return

        if e.ShiftDown():
            if e.LeftDown() and self.SelectedPointIndex is None:
                self.SelectedPointIndex = self.TransformController.TryAddPoint(ImageX, ImageY,
                                                                               space=self.space)
                if e.AltDown():
                    self.TransformController.AutoAlignPoints(self.SelectedPointIndex)

                history.SaveState(self.TransformController.SetPoints, self.TransformController.points)
            elif e.RightDown():
                self.TransformController.TryDeletePoint(ImageX, ImageY, self.SelectionMaxDistance,
                                                        space=self.space)
                if self.SelectedPointIndex is not None:
                    if self.SelectedPointIndex > self.TransformController.NumPoints:
                        self.SelectedPointIndex = self.TransformController.NumPoints - 1

                history.SaveState(self.TransformController.SetPoints, self.TransformController.points)

        elif e.LeftDown():
            if e.AltDown() and not self.HighlightedPointIndex is None:
                self.TransformController.SetPoint(self.HighlightedPointIndex, ImageX, ImageY,
                                                  space=self.space)
                history.SaveState(self.TransformController.SetPoints, self.TransformController.points)
            else:
                distance, index = (None, None)
                if not self.composite:
                    distance, index = self.TransformController.NearestPoint((ImageY, ImageX),
                                                                            space=self.space)
                else:
                    distance, index = self.TransformController.NearestPoint((ImageY, ImageX), space=self.space)

                if distance is None:
                    return

                print("d: " + str(distance) + " to p# " + str(index) + " max d: " + str(self.SelectionMaxDistance))
                self.SelectedPointIndex = index if distance < self.SelectionMaxDistance else None

    def on_mouse_drag(self, e):

        (y, x) = self.GetCorrectedMousePosition(e)

        if self.LastMousePosition is None:
            self.LastMousePosition = (y, x)
            return

        dx = x - self.LastMousePosition[nornir_imageregistration.iPoint.X]
        dy = (y - self.LastMousePosition[nornir_imageregistration.iPoint.Y])

        self.LastMousePosition = (y, x)

        ImageY, ImageX = self.camera.ImageCoordsForMouse(y, x)
        if ImageX is None:
            return

        ImageDX = (float(dx) / self.width) * self.camera.ViewWidth
        ImageDY = (float(dy) / self.height) * self.camera.ViewHeight

        if e.RightIsDown():
            self.camera.lookat = (self.camera.y - ImageDY, self.camera.x - ImageDX)

        if e.LeftIsDown():
            if e.CmdDown():
                # Translate all points
                self.TransformController.TranslateFixed((ImageDY, ImageDX))
            else:
                # Create a point or drag a point
                if not self.SelectedPointIndex is None:
                    self.SelectedPointIndex = self.TransformController.MovePoint(self.SelectedPointIndex, ImageDX,
                                                                                 ImageDY, space=self.space)
                elif e.ShiftDown():  # The shift key is selected and we do not have a last point dragged
                    return
                else:
                    # find nearest point
                    self.SelectedPointIndex = self.TransformController.TryDrag(ImageX, ImageY, ImageDX, ImageDY,
                                                                               self.SelectionMaxDistance,
                                                                               space=self.space)

        self.statusBar.update_status_bar(self.LastMousePosition, in_target_space=self.FixedSpace)
