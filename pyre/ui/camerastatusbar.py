import nornir_imageregistration
from pyre import state
import pyre.viewmodels
from pyre.ui import Camera

try:
    import wx
except:
    print("Ignoring wx import failure, assumed documentation use, otherwise please install wxPython")


class CameraStatusBar(wx.StatusBar):

    @property
    def camera(self) -> Camera:
        return self._camera

    @camera.setter
    def camera(self, value):
        self._camera = value

    @property
    def TransformController(self) -> pyre.viewmodels.TransformController:
        return state.currentStosConfig.TransformController

    def __init__(self, parent: wx.Window, camera: Camera, **kwargs):
        self._camera = camera
        # self._TransformController = transformController
        super(CameraStatusBar, self).__init__(parent, **kwargs)
        self.SetFieldsCount(3)

    def update_status_bar(self, point, in_target_space: bool = False):
        """
        :param point:
        :param in_target_space: If true, the point is in target space, otherwise it is in source space
        :return:
        """
        if self.camera is None:
            return

        if point is None:
            return

        # mousePosTemplate = '%d x, %d y, %4.2f%%

        point = self.camera.ImageCoordsForMouse(point[nornir_imageregistration.iPoint.Y],
                                                point[nornir_imageregistration.iPoint.X])

        zoom_percentage = (1.0 / (float(self.camera.scale) / float(self.camera.WindowHeight))) * 100.0
        # mousePosStr = mousePosTemplate % (x, y, ZoomValue)

        source_point = None
        target_point = None

        if in_target_space:
            target_point = point
            source_point = None if self.TransformController is None else self.TransformController.InverseTransform(
                target_point).flat
        else:
            source_point = point
            target_point = None if self.TransformController is not None else self.TransformController.Transform(
                point).flat

        # self.SetStatusText('%dx, %dy' % (point[nornir_imageregistration.iPoint.X], point[nornir_imageregistration.iPoint.Y]), 0)

        src_txt = f'Source/Warped: {source_point[nornir_imageregistration.iPoint.X]: 0.1f}x {source_point[nornir_imageregistration.iPoint.Y]: 0.1f}y' if source_point is not None else ''
        self.SetStatusText(src_txt, 0)
        tgt_txt = f'Target/Fixed: {target_point[nornir_imageregistration.iPoint.X]: 0.1f}x {target_point[nornir_imageregistration.iPoint.Y]: 0.1f}y' if target_point is not None else ''
        self.SetStatusText(tgt_txt, 1)

        self.SetStatusText('Zoom: %4.2f%%' % zoom_percentage, 2)

        self.Refresh()
