from __future__ import annotations

from dependency_injector.wiring import Provide, inject

import nornir_imageregistration
from pyre.space import Space
from pyre.interfaces.readonlycamera import IReadOnlyCamera
import pyre.controllers.transformcontroller
from pyre.interfaces.managers.mousepositionhistorymanager import IMousePositionHistoryManager
from pyre.container import IContainer

try:
    import wx
except:
    print("Ignoring wx import failure, assumed documentation use, otherwise please install wxPython")


class CameraStatusBar(wx.StatusBar):
    _camera_window: wx.Window  # Window that the camera is rendering to and we track mouse events on
    _window_height: int
    _window_width: int

    _mouse_position_history_manager: IMousePositionHistoryManager

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

    @inject
    def __init__(self,
                 parent: wx.Window,
                 camera: IReadOnlyCamera,
                 camera_window: wx.Window,
                 mouse_position_history_manager: IMousePositionHistoryManager = Provide[
                     IContainer.mouse_position_history],
                 **kwargs):
        self._camera = camera
        self._camera_window = camera_window
        # self._space = space
        super(CameraStatusBar, self).__init__(parent, **kwargs)
        self.SetFieldsCount(3)
        # self._camera_window.Bind(wx.EVT_MOTION, self.OnMouseMotion)
        parent.Bind(wx.EVT_SIZE, self.OnSize)
        parent.Bind(wx.EVT_SIZING, self.OnSize)
        self._camera.AddOnChangeEventListener(self.OnCameraChanged)

        self._window_width, self._window_height = self._camera_window.GetSize()
        wx.CallAfter(self.OnSize, None)

        mouse_position_history_manager.add_mouse_position_update_event_listener(self.on_position_update)

    def OnCameraChanged(self):
        if self._window_height != 0:
            zoom_percentage = self.camera.scale * 100.0
            self.SetStatusText('Zoom: %4.2f%%' % zoom_percentage, 2)
        else:
            self.SetStatusText('Zoom: 100%', 2)

    def on_position_update(self, space: Space, position: tuple[float, float]):
        self.update_status_bar(space, position)

    def OnSize(self, event):
        self._window_width, self._window_height = self._camera_window.GetSize()

        if event is not None:
            event.Skip()

    def update_status_bar(self, space: Space, point: tuple[float, float]):
        if space == Space.Source:
            src_txt = f'Source/Warped: {point[nornir_imageregistration.iPoint.X]: 0.1f}x {point[nornir_imageregistration.iPoint.Y]: 0.1f}y' if point is not None else ''
            self.SetStatusText(src_txt, 0)
        elif space == Space.Target:
            tgt_txt = f'Target/Fixed: {point[nornir_imageregistration.iPoint.X]: 0.1f}x {point[nornir_imageregistration.iPoint.Y]: 0.1f}y' if point is not None else ''
            self.SetStatusText(tgt_txt, 1)
        else:
            raise ValueError("Invalid space")

        self.Refresh()
