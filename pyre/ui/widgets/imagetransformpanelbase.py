"""
Created on Feb 6, 2015

@author: u0490822
"""
from abc import abstractmethod

import numpy as np

from pyre.interfaces.managers import IGLContextManager

try:
    import wx
except:
    print("Ignoring wx import failure, assumed documentation use, otherwise please install wxPython")

from dependency_injector.wiring import Provide, inject
import nornir_imageregistration
from pyre.ui import Camera
from pyre.ui.widgets import glpanel
from pyre.ui.widgets.camerastatusbar import CameraStatusBar
from pyre.controllers.transformcontroller import TransformController
from pyre.container import IContainer


class ImageTransformPanelBase:
    """
    Contains a GLContext and a camera to render a scene
    """
    _camera: Camera
    _glpanel: glpanel.GLPanel
    _width: int
    _height: int
    _statusbar: CameraStatusBar
    _transform_controller: TransformController

    _glcontextmanager: IGLContextManager = Provide[IContainer.glcontext_manager]

    @property
    def statusbar(self) -> CameraStatusBar:
        return self._statusbar

    @property
    def glcanvas(self):
        """The GLCanvas that renders the scene"""
        return self._glpanel

    @property
    def camera(self) -> Camera:
        """Camera position information for the scene being rendered on the glcanvas"""
        return self._camera

    @camera.setter
    def camera(self, value: Camera | None):

        if self._camera is not None:
            self._camera.RemoveOnChangeEventListener(self.OnCameraChanged)

        self._camera = value

        if value is not None:
            assert (isinstance(value, Camera))
            value.AddOnChangeEventListener(self.OnCameraChanged)

    @property
    def transform_controller(self) -> TransformController:
        return self._transform_controller

    @property
    def width(self) -> int:
        """Width of the image in pixels"""
        return self._width

    @property
    def height(self) -> int:
        """Height of the image in pixels"""
        return self._height

    @inject
    def __init__(self,
                 parent: wx.Window,
                 transform_controller: TransformController,
                 window_id: int = wx.ID_ANY, **kwargs):
        """
        Constructor
        """
        self._parent = parent
        self._transform_controller = transform_controller
        self._glpanel = glpanel.GLPanel(parent=parent,
                                        draw_method=self.draw,
                                        window_id=window_id,
                                        **kwargs)

        self.sizer = wx.BoxSizer(wx.VERTICAL)

        self.sizer.Add(self._glpanel, 1, wx.EXPAND)
        parent.SetSizer(self.sizer)
        self.sizer.Fit(parent)
        parent.Layout()

        self._camera = Camera((0, 0), 1)

        # self._glpanel.Bind(wx.EVT_SIZING, self.on_resize)
        parent.Bind(wx.EVT_SIZE, self.on_resize)

        self._width, self._height = self._glpanel.GetClientSize()
        self.AddStatusBar()

        self._camera.AddOnChangeEventListener(self.OnCameraChanged)

        self._glpanel.Bind(wx.EVT_ENTER_WINDOW, handler=self.on_mouse_enter)

    def on_mouse_enter(self, e):
        self._parent.SetFocus()
        e.Skip()

    def AddStatusBar(self):
        self._statusbar = CameraStatusBar(self._parent,
                                          self.camera,
                                          self.glcanvas)
        self.sizer.Add(self._statusbar, flag=wx.BOTTOM | wx.EXPAND)
        self._statusbar.SetFieldsCount(3)

    def __str__(self, *args, **kwargs):
        return self._glpanel.TopLevelParent.Label

    def ImageCoordsForMouse(self, y: float, x) -> tuple[float, float]:
        return self.camera.ImageCoordsForMouse(y, x)

    def on_resize(self, e: wx.SizeEvent):
        # There seems to be latency in the GLPanel size being updated,
        # so we need to wait for the next message
        wx.CallAfter(self.update_size)
        e.Skip()

    def update_size(self):
        """Update the size of the camera and the camera's view of the world.
        This is called when the window is resized, but on a later message since
        there seems to be a latency in the glpanel size being updated"""
        (self._width, self._height) = self._glpanel.GetClientSize()
        # (self._width, self._height) = e.Size.width, e.Size.height
        if self.camera is not None and self._width > 0 and self._height > 0:
            # try:
            print(f"Setting window size to {self._height}h x {self._width}w")
            self.camera.window_size = np.array((self._height, self._width))
            self.camera.focus(self.height, self.width)
            # except:
            # pass

    def GetCorrectedMousePosition(self, e) -> tuple[float, float]:
        """wxPython inverts the mouse position, flip it back"""
        (x, y) = e.GetPosition()
        return self.height - y, x

    def OnTransformChanged(self):
        self._glpanel.Refresh()

    def OnCameraChanged(self):
        self._glpanel.Refresh()

    def lookatfixedpoint(self, point: nornir_imageregistration.PointLike, scale: float):
        """specify a point to look at in fixed space"""
        self.camera.lookat = point
        self.camera.scale = scale

    @abstractmethod
    def center_camera(self):
        """
        Center the camera at whatever interesting thing this class displays
        """
        raise NotImplementedError()

    # def center_camera(self):
    #     """Center the camera at whatever interesting thing this class displays
    #     """
    #
    #     if isinstance(self.transform_controller.TransformModel, nornir_imageregistration.IDiscreteTransform):
    #         fixed_bounding_box = self.transform_controller.TransformModel.FixedBoundingBox
    #     elif self.width is not None:
    #         fixed_bounding_box = nornir_imageregistration.Rectangle.CreateFromPointAndArea((0, 0), (
    #             self.height, self.width))
    #     else:
    #         return
    #         # raise NotImplementedError("Not done")
    #
    #     self.camera.lookat = fixed_bounding_box.Center
    #     if self.transform_controller.width is None and self.transform_controller.width != 0:
    #         self.camera.scale = fixed_bounding_box.Width / self.transform_controller.width
    #
    #
    #     return

    @abstractmethod
    def draw(self):
        """Draw the image in either source (fixed) or target (warped) space
        :param view_proj: View projection matrix"""
        raise NotImplementedError()
