

import nornir_imageregistration
from pyre import state
import wx


class CameraStatusBar(wx.StatusBar):

    @property
    def camera(self):
        return self._camera

    @camera.setter
    def camera(self, value):
        self._camera = value

    @property
    def TransformController(self):
        return state.currentStosConfig.TransformController

    def __init__(self, parent, camera, **kwargs):
        self._camera = camera
        # self._TransformController = transformController
        super(CameraStatusBar, self).__init__(parent, **kwargs)
        self.SetFieldsCount(3)

    def update_status_bar(self, point):
        if self.camera is None:
            return

        if point is None:
            return
        # mousePosTemplate = '%d x, %d y, %4.2f%%

        point = self.camera.ImageCoordsForMouse(point[nornir_imageregistration.iPoint.Y], point[nornir_imageregistration.iPoint.X])

        ZoomValue = (1.0 / (float(self.camera.scale) / float(self.camera.WindowHeight))) * 100.0
        # mousePosStr = mousePosTemplate % (x, y, ZoomValue)
        transformed_point = (0, 0)

        if not self.TransformController is None:
            transformed_point = self.TransformController.Transform(point)

        self.SetStatusText('%dx, %dy' % (point[nornir_imageregistration.iPoint.X], point[nornir_imageregistration.iPoint.Y]), 0)
        self.SetStatusText('%dx, %dy' % (transformed_point[0][nornir_imageregistration.iPoint.X], transformed_point[0][nornir_imageregistration.iPoint.Y]), 1)
        self.SetStatusText('%4.2f%%' % ZoomValue, 1)
        
        self.Refresh()
