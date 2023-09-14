'''
Created on Feb 6, 2015

@author: u0490822
'''

import operator

import nornir_imageregistration
import nornir_imageregistration.spatial
import pyre.state as state

try:
    import wx
except:
    print("Ignoring wx import failure, assumed documentation use, otherwise please install wxPython")

from . import imagetransformpanelbase
import nornir_imageregistration.transforms.utils as utils
import pyglet.gl as gl
import pyre.ui
import pyre.views


def _get_ITV_transform(ITV):
    '''Return the transform for an ImageTransformView'''
    return ITV.Transform


def _get_transforms(ImageTransformViewList):
    return list(map(_get_ITV_transform, ImageTransformViewList))


class MosaicTransformPanel(imagetransformpanelbase.ImageTransformPanelBase):
    '''
    Displays a list of ImageTransformViews to render a mosaic
    '''

    @property
    def ImageTransformViewList(self):
        return self._imageTransformViewList

    @ImageTransformViewList.setter
    def ImageTransformViewList(self, value):
        self._imageTransformViewList = value

    @property
    def Command(self):
        return self._command

    @Command.setter
    def Command(self, value):
        self._command = value

    def __init__(self, parent, window_id=-1, imageTransformViewList=None, **kwargs):
        '''
        Constructor
        '''
        if imageTransformViewList is None:
            imageTransformViewList = []

        super(MosaicTransformPanel, self).__init__(parent, window_id, **kwargs)

        state.currentMosaicConfig.AddOnMosaicChangeEventListener(self.OnMosaicChanged)
        self._imageTransformViewList = imageTransformViewList

        self.LastMousePosition = None

        self._bind_mouse_events()

        self.AddStatusBar()

        self.Command = None

    def OnMosaicChanged(self):
        self.ImageTransformViewList = state.currentMosaicConfig.ImageTransformViewList
        self.center_camera()

    def _bind_mouse_events(self):
        self.canvas.Bind(wx.EVT_MOUSEWHEEL, self.on_mouse_scroll)
        self.canvas.Bind(wx.EVT_MOTION, self.on_mouse_drag)
        self.canvas.Bind(wx.EVT_LEFT_DOWN, self.on_mouse_press)
        self.canvas.Bind(wx.EVT_MIDDLE_DOWN, self.on_mouse_press)
        self.canvas.Bind(wx.EVT_RIGHT_DOWN, self.on_mouse_press)

    def AddStatusBar(self):
        self.statusBar = pyre.ui.camerastatusbar.CameraStatusBar(self, self.camera)
        self.sizer.Add(self.statusBar, flag=wx.BOTTOM | wx.EXPAND)

    def center_camera(self):
        '''Center the camera at whatever interesting thing this class displays
        '''

        transforms = _get_transforms(self.ImageTransformViewList)
        bbox = utils.FixedBoundingBox(transforms)
        bbox_rect = nornir_imageregistration.spatial.Rectangle.CreateFromBounds(bbox)
        self.camera.lookat(bbox_rect.Center)
        self.camera.scale = bbox_rect.Width

    def draw_objects(self):

        self.camera.focus(self.width, self.height)

        pointScale = self.camera.scale / self.height

        pyre.views.SetDrawMosaicState()

        bounding_box = self.camera.VisibleImageBoundingBox

        for itv in self.ImageTransformViewList:
            itv.draw_textures(ShowWarped=True, BoundingBox=bounding_box, glFunc=gl.GL_FUNC_ADD)

        pyre.views.ClearDrawTextureState()

        for itv in self.ImageTransformViewList:
            itv.draw_points(SelectedIndex=None, BoundingBox=self.camera.VisibleImageBoundingBox, FixedSpace=True,
                            ScaleFactor=pointScale)

        if not self.Command is None:
            self.Command.draw()

    def on_mouse_press(self, e):
        (y, x) = self.GetCorrectedMousePosition(e)
        ImageY, ImageX = self.camera.ImageCoordsForMouse(y, x)

        if ImageX is None or ImageY is None:
            return

        if e.LeftIsDown():
            self.Command = pyre.ui.rectangle_command.RectangleCommand(self.canvas, self.on_rectange_command_completed,
                                                                      self.camera, (ImageY, ImageX), )

        if e.MiddleIsDown():
            self.center_camera()

    def on_mouse_drag(self, e):

        (y, x) = self.GetCorrectedMousePosition(e)

        if e.LeftIsDown() and not self.Command is None:
            self.Command.on_mouse_drag(e)

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
            self.camera.lookat((self.camera.y - ImageDY, self.camera.x - ImageDX))

        self.statusBar.update_status_bar(self.LastMousePosition)

        self.canvas.Refresh()

    def on_mouse_scroll(self, e):

        if self.camera is None:
            return

        scroll_y = e.GetWheelRotation() / 120.0

        # We rotate when command is down
        if e.CmdDown():
            angle = float(abs(scroll_y) / 4.0) ** 2.0

            if angle > 15.0:
                angle = 15.0

            rangle = (angle / 180.0) * 3.14159
            if scroll_y < 0:
                rangle = -rangle

        else:
            zdelta = (1 + (-scroll_y / 20.0))
            self.camera.scale *= zdelta

        self.statusBar.update_status_bar(self.LastMousePosition)

        self.canvas.Refresh()

    def on_rectange_command_completed(self, RectangleCommand):
        self.Command = None
        return
