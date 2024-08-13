import nornir_imageregistration
from pyre import state
from pyre.state import Space
import pyre.viewmodels
from pyre.ui import IReadOnlyCamera

try:
    import wx
except:
    print("Ignoring wx import failure, assumed documentation use, otherwise please install wxPython")


class CameraStatusBar(wx.StatusBar):
    _camera_window: wx.Window  # Window that the camera is rendering to and we track mouse events on
    _window_height: int
    _window_width: int
    _space: Space  # Space that mouse coordinates arrive in

    @property
    def camera(self) -> IReadOnlyCamera:
        return self._camera

    @camera.setter
    def camera(self, value: IReadOnlyCamera):
        self._camera = value

    @property
    def space(self) -> Space:
        return self._space

    @space.setter
    def space(self, value: Space):
        self._space = value

    @property
    def TransformController(self) -> pyre.viewmodels.TransformController:
        return state.currentStosConfig.TransformController

    def __init__(self, parent: wx.Window,
                 camera: IReadOnlyCamera,
                 camera_window: wx.Window,  # Window that the camera is rendering to and we track mouse events on
                 space: Space = Space.Target,  # Space that mouse coordinates arrive in
                 **kwargs):
        self._camera = camera
        self._camera_window = camera_window
        self._space = space
        # self._TransformController = transformController
        super(CameraStatusBar, self).__init__(parent, **kwargs)
        self.SetFieldsCount(3)
        self._camera_window.Bind(wx.EVT_MOTION, self.OnMouseMotion)
        parent.Bind(wx.EVT_SIZE, self.OnSize)
        parent.Bind(wx.EVT_SIZING, self.OnSize)
        self._camera.AddOnChangeEventListener(self.OnCameraChanged)

        self._window_width, self._window_height = self._camera_window.GetSize()
        wx.CallAfter(self.OnSize, None)

    def OnCameraChanged(self):
        if self._window_height != 0:
            zoom_percentage = (1.0 / (float(self.camera.scale) / float(self._window_height))) * 100.0
            self.SetStatusText('Zoom: %4.2f%%' % zoom_percentage, 2)
        else:
            self.SetStatusText('Zoom: 100%', 2)

    def OnMouseMotion(self, event):
        screen_pos = self.get_corrected_mouse_position(event)
        world_position = self._camera.ImageCoordsForMouse(screen_pos[nornir_imageregistration.iPoint.Y],
                                                          screen_pos[nornir_imageregistration.iPoint.X])
        self.update_status_bar(world_position)
        event.Skip()

    def OnSize(self, event):
        self._window_width, self._window_height = self._camera_window.GetSize()

        if event is not None:
            event.Skip()

    def get_corrected_mouse_position(self, event) -> tuple[float, float]:
        """
        :param event: wx.MouseEvent
        :return: (x, y) tuple of the corrected mouse position
        """
        (x, y) = event.GetPosition()
        return self._window_height - y, x

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

        source_point = None
        target_point = None

        if self.space == pyre.state.Space.Target:
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

        self.Refresh()
