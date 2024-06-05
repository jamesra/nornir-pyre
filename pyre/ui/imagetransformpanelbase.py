"""
Created on Feb 6, 2015

@author: u0490822
"""
import pyre.state

try:
    import wx
except:
    print("Ignoring wx import failure, assumed documentation use, otherwise please install wxPython")

import nornir_imageregistration
import nornir_imageregistration.spatial as spatial
from pyre.ui import glpanel, Camera
from pyre.ui.camerastatusbar import CameraStatusBar


class ImageTransformPanelBase(glpanel.GLPanel):
    """
    classdocs
    """

    _camera: Camera

    @property
    def camera(self) -> Camera:
        return self._camera

    @camera.setter
    def camera(self, value: Camera | None):

        if self._camera is not None:
            self._camera.RemoveOnChangeEventListener(self.OnCameraChanged)

        self._camera = value

        if value is not None:
            assert (isinstance(value, Camera))
            value.AddOnChangeEventListener(self.OnCameraChanged)

    def __init__(self,
                 parent: wx.Window,
                 glcontextmanager: pyre.state.IGLContextManager,
                 window_id: int = -1, **kwargs):
        """
        Constructor
        """
        self._camera = Camera((0, 0), 1)

        super(ImageTransformPanelBase, self).__init__(parent=parent,
                                                      glcontextmanager=glcontextmanager,
                                                      window_id=window_id,
                                                      **kwargs)

        self.width, self.height = self.GetSize()

        self.AddStatusBar()

        self._camera.AddOnChangeEventListener(self.OnCameraChanged)

        pass

    def AddStatusBar(self):
        self.statusBar = CameraStatusBar(self, self.camera)
        self.sizer.Add(self.statusBar, flag=wx.BOTTOM | wx.EXPAND)
        self.statusBar.SetFieldsCount(3)

    def __str__(self, *args, **kwargs):
        return self.TopLevelParent.Label

    def update(self, dt):
        pass

    def ImageCoordsForMouse(self, y: float, x) -> tuple[float, float]:
        return self.camera.ImageCoordsForMouse(y, x)

    def on_resize(self, e):
        (self.width, self.height) = self.canvas.GetSize()
        if self.camera is not None:
            # try:
            self.camera.focus(self.height, self.width)
            # except:
            # pass

    def GetCorrectedMousePosition(self, e) -> tuple[float, float]:
        """wxPython inverts the mouse position, flip it back"""
        (x, y) = e.GetPosition()
        return self.height - y, x

    def OnTransformChanged(self):
        self.canvas.Refresh()

    def OnCameraChanged(self):
        self.canvas.Refresh()

    def lookatfixedpoint(self, point: nornir_imageregistration.PointLike, scale: float):
        """specify a point to look at in fixed space"""
        self.camera.lookat = point
        self.camera.scale = scale

    def center_camera(self):
        """Center the camera at whatever interesting thing this class displays
        """

        raise NotImplementedError("Abstract function center_camera not implemented")

    def draw_objects(self):
        raise NotImplementedError("draw object is not implemented")
