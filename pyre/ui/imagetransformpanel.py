'''
Created on Oct 16, 2012

@author: u0490822
'''

import math

import os
import numpy as np
import nornir_imageregistration
import OpenGL.GL as gl
# import pyglet
# from pyglet import *

import pyre.state
from pyre import history, state
import wx

from . import imagetransformpanelbase
from pyre.ui import Camera
from pyre.viewmodels import TransformController
from pyre.views import CompositeTransformView, ImageGridTransformView, SetDrawTextureState, ClearDrawTextureState


class ImageTransformViewPanel(imagetransformpanelbase.ImageTransformPanelBase):
    '''
    classdocs
    '''
    _CurrentDragPoint = None  # type: int | None
    _HighlightedPointIndex = 0  # type: int | None

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
    def ImageGridTransformView(self):
        return self._ImageTransformView

    @ImageGridTransformView.setter
    def ImageGridTransformView(self, value):

        self._ImageTransformView = value

        if value is None:
            return
        else:
            assert (isinstance(value, ImageGridTransformView))

        (self.width, self.height) = self.canvas.GetSize()

        self.center_camera()

    @property
    def SelectionMaxDistance(self) -> float:
        selectionMaxDistance = (float(self.camera.ViewHeight) / float(self.height)) * 20.0
        if selectionMaxDistance < 16:
            selectionMaxDistance = 16

        return selectionMaxDistance

    def __init__(self, parent, id=-1, TransformController=None, ImageGridTransformView: ImageGridTransformView = None,
                 FixedSpace: bool = False,
                 composite: bool = False, **kwargs):
        '''
        Constructor
        :param composite: true if we are showing a composite image, if false we are using FixedSpace to determine the image we are showing
        :param FixedSpace: true if we are showing the fixed space image, if false we are showing the warped image
        '''
        self._ImageTransformView = None

        super(ImageTransformViewPanel, self).__init__(parent, id, **kwargs)

        self.ImageGridTransformView = ImageGridTransformView

        state.currentStosConfig.AddOnTransformControllerChangeEventListener(self.OnTransformViewModelChanged)
        state.currentStosConfig.AddOnImageViewModelChangeEventListener(self.OnImageViewModelChanged)

        # self.schedule = clock.schedule_interval(func = self.update, interval = 1 / 2.)
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_timer)

        (self.width, self.height) = self.canvas.GetSize()

        # wx.EVT_TIMER(self, -1, self.on_timer)

        self.ShowLines = False

        self.LastMousePosition = None

        self.FixedSpace = FixedSpace

        self.ShowWarped = False

        self.glFunc = gl.GL_FUNC_ADD

        self.composite = composite

        self.LastMousePosition = None

        self.LastDrawnBoundingBox = None

        self._bind_mouse_events()

        self.Bind(wx.EVT_KEY_DOWN, self.on_key_press)
        self.canvas.Bind(wx.EVT_KEY_DOWN, self.on_key_press)
        self.canvas.Bind(wx.EVT_SIZE, self.on_resize)

        self.DebugTickCounter = 0
        self.timer.Start(500)

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

    def OnTransformViewModelChanged(self):
        if self.ImageGridTransformView is not None:
            self.ImageGridTransformView.TransformController = state.currentStosConfig.TransformController

        self.canvas.Refresh()

    def _LabelPreamble(self):
        if self.FixedSpace:
            return "Fixed: "
        else:
            return "Warping: "

    def OnImageViewModelChanged(self, FixedImage):

        if self.composite:
            self.UpdateRawImageWindow()
        elif self.FixedSpace == FixedImage:
            self.UpdateRawImageWindow()
            if self.ImageGridTransformView.ImageViewModel is not None:
                self.TopLevelParent.Label = self._LabelPreamble() + os.path.basename(
                    self.ImageGridTransformView.ImageViewModel.ImageFilename)

        # self.lookatfixedpoint((0,0), 1.0)

        self.center_camera()
        self.canvas.Refresh()

    def UpdateRawImageWindow(self):
        if self.composite:
            if not (
                    state.currentStosConfig.FixedImageViewModel is None or state.currentStosConfig.WarpedImageViewModel is None):
                self.ImageGridTransformView = CompositeTransformView(state.currentStosConfig.FixedImageViewModel,
                                                                     state.currentStosConfig.WarpedImageViewModel,
                                                                     state.currentStosConfig.TransformController)
        elif not self.FixedSpace:
            self.ImageGridTransformView = ImageGridTransformView(state.currentStosConfig.WarpedImageViewModel,
                                                                 state.currentStosConfig.WarpedImageMaskViewModel,
                                                                 Transform=state.currentStosConfig.TransformController)
        else:
            self.ImageGridTransformView = ImageGridTransformView(state.currentStosConfig.FixedImageViewModel,
                                                                 state.currentStosConfig.FixedImageMaskViewModel,
                                                                 Transform=state.currentStosConfig.TransformController)

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
            self.ShowLines = not self.ShowLines
        elif keycode == wx.WXK_F1:
            self._ImageTransformView.Debug = not self._ImageTransformView.Debug
        elif symbol == 'm':
            LookAt = [self.camera.y, self.camera.x]

            # if not self.FixedSpace and self.ShowWarped:
            #    LookAt = self.TransformController.Transform([LookAt])
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
        '''specify a point to look at in fixed space'''

        if not self.FixedSpace:
            if not self.ShowWarped:
                if not self.TransformController is None:
                    point = self.TransformController.InverseTransform([point]).flat

        super(ImageTransformViewPanel, self).lookatfixedpoint(point, scale)

    def center_camera(self):
        '''Center the camera at whatever interesting thing this class displays
        '''

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
        '''Region is [x,y,TextureWidth,TextureHeight] indicating where the image should be drawn on the window'''

        if self._ImageTransformView is None or self.camera is None:
            return

        self.camera.focus(self.width, self.height)

        BoundingBox = self.camera.VisibleImageBoundingBox

        SetDrawTextureState()

        # Draw an image if we can
        if not self.composite:
            self._ImageTransformView.draw_textures(self.camera.view_proj, BoundingBox=BoundingBox,
                                                   ShowWarped=self.ShowWarped,
                                                   glFunc=gl.GL_FUNC_ADD)
        else:
            self._ImageTransformView.draw_textures(self.camera.view_proj, BoundingBox=BoundingBox, glFunc=self.glFunc)

        ClearDrawTextureState()

        if self.TransformController is None:
            return

        FixedSpacePoints = self.FixedSpace
        FixedSpaceLines = FixedSpacePoints
        if self.composite:
            FixedSpacePoints = False
            FixedSpaceLines = True
        else:
            # This looks backwards, and it is.  The transform object itself refers to warped and fixed space.  Depending on how warped is interpreted it means 
            # the points that are warped or the points that have been warped.  It needs to be refactored to make the names unabiguous
            FixedSpacePoints = self.FixedSpace or self.ShowWarped
            FixedSpaceLines = self.FixedSpace or self.ShowWarped

        if self.ShowLines:
            self._ImageTransformView.draw_lines(draw_in_fixed_space=FixedSpaceLines)

        # pointScale = (BoundingBox[3] * BoundingBox[2]) / (self.height * self.width)
        pointScale = self.camera.scale / self.height
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

            # if isinstance(self.TransformController.TransformModel, nornir_imageregistration.ITransformTargetRotation):
            #     self.TransformController.TransformModel.RotateTargetPoints(-rangle,
            #                                       (state.currentStosConfig.FixedImageMaskViewModel.RawImageSize[0] / 2.0,
            #                                        state.currentStosConfig.FixedImageMaskViewModel.RawImageSize[1] / 2.0))
            # elif isinstance(self.TransformController.TransformModel, nornir_imageregistration.ITransformSourceRotation):
            #     self.TransformController.TransformModel.RotateSourcePoints(rangle,
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
                                                                               FixedSpace=self.FixedSpace)
                if e.AltDown():
                    self.TransformController.AutoAlignPoints(self.SelectedPointIndex)

                history.SaveState(self.TransformController.SetPoints, self.TransformController.points)
            elif e.RightDown():
                self.TransformController.TryDeletePoint(ImageX, ImageY, self.SelectionMaxDistance,
                                                        FixedSpace=self.FixedSpace)
                if self.SelectedPointIndex is not None:
                    if self.SelectedPointIndex > self.TransformController.NumPoints:
                        self.SelectedPointIndex = self.TransformController.NumPoints - 1

                history.SaveState(self.TransformController.SetPoints, self.TransformController.points)

        elif e.LeftDown():
            if e.AltDown() and not self.HighlightedPointIndex is None:
                self.TransformController.SetPoint(self.HighlightedPointIndex, ImageX, ImageY,
                                                  FixedSpace=self.FixedSpace)
                history.SaveState(self.TransformController.SetPoints, self.TransformController.points)
            else:
                distance, index = (None, None)
                if not self.composite:
                    distance, index = self.TransformController.NearestPoint((ImageY, ImageX),
                                                                            FixedSpace=self.ShowWarped)
                else:
                    distance, index = self.TransformController.NearestPoint((ImageY, ImageX), FixedSpace=True)

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
                                                                                 ImageDY, FixedSpace=self.FixedSpace)
                elif e.ShiftDown():  # The shift key is selected and we do not have a last point dragged
                    return
                else:
                    # find nearest point
                    self.SelectedPointIndex = self.TransformController.TryDrag(ImageX, ImageY, ImageDX, ImageDY,
                                                                               self.SelectionMaxDistance,
                                                                               FixedSpace=self.FixedSpace)

        self.statusBar.update_status_bar(self.LastMousePosition, in_target_space=self.FixedSpace)
