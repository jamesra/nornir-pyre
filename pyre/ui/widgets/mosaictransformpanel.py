'''
Created on Feb 6, 2015

@author: u0490822
'''

import nornir_imageregistration
import nornir_imageregistration.spatial
import pyre.state as state

from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QPoint, pyqtSignal
from PyQt6.QtGui import QWheelEvent, QMouseEvent

from dependency_injector.wiring import Provide, inject
from pyre.container import IContainer
from pyre.controllers.transformcontroller import TransformController
from pyre.ui.widgets import imagetransformpanelbase
import nornir_imageregistration.transforms.utils as utils
import OpenGL.GL as gl
import pyre.ui
import pyre.views


def _get_ITV_transform(ITV):
    '''Return the transform for an ImageTransformView'''
    return ITV.transform


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

    @inject
    def __init__(self,
                 parent,
                 imageTransformViewList=None,
                 transform_controller: TransformController = Provide[IContainer.transform_controller],
                 **kwargs):
        '''
        Constructor
        '''
        if imageTransformViewList is None:
            imageTransformViewList = []

        super(MosaicTransformPanel, self).__init__(parent, transform_controller=transform_controller, **kwargs)

        state.currentMosaicConfig.AddOnMosaicChangeEventListener(self.OnMosaicChanged)
        self._imageTransformViewList = imageTransformViewList

        self.LastMousePosition = None

        self._bind_mouse_events()

        self.addStatusBar()

        self.Command = None

    def OnMosaicChanged(self):
        self.ImageTransformViewList = state.currentMosaicConfig.ImageTransformViewList
        self.center_camera()

    def _bind_mouse_events(self):
        # Connect mouse events to the glcanvas
        self.glcanvas.wheelEvent = self.on_mouse_scroll
        self.glcanvas.mouseMoveEvent = self.on_mouse_drag
        self.glcanvas.mousePressEvent = self.on_mouse_press

    def addStatusBar(self):
        self.statusBar = pyre.ui.widgets.camerastatusbar.CameraStatusBar(self,
                                                                         self.camera,
                                                                         self.glcanvas)
        self.layout.addWidget(self.statusBar)

    def center_camera(self):
        '''Center the camera at whatever interesting thing this class displays
        '''
        transforms = _get_transforms(self.ImageTransformViewList)
        bbox = utils.FixedBoundingBox(transforms)
        bbox_rect = nornir_imageregistration.spatial.Rectangle.CreateFromBounds(bbox)
        self.camera.lookat = bbox_rect.Center
        self.camera.scale = bbox_rect.Width

    def draw(self):
        self.camera.focus(self.width, self.height)

        pointScale = self.camera.scale / self.height

        pyre.views.SetDrawMosaicState()

        bounding_box = self.camera.VisibleImageBoundingBox

        for itv in self.ImageTransformViewList:
            itv.draw(ShowWarped=True, bounding_box=bounding_box, glFunc=gl.GL_FUNC_ADD)

        pyre.views.ClearDrawTextureState()

        for itv in self.ImageTransformViewList:
            itv.draw_points(SelectedIndex=None, BoundingBox=self.camera.VisibleImageBoundingBox, FixedSpace=True,
                            ScaleFactor=pointScale)

        if self.Command is not None:
            self.Command.draw()

    def on_mouse_press(self, event: QMouseEvent):
        (y, x) = self.getCorrectedMousePosition(event)
        ImageY, ImageX = self.camera.ImageCoordsForMouse(y, x)

        if ImageX is None or ImageY is None:
            return

        if event.button() == Qt.MouseButton.LeftButton:
            self.Command = pyre.ui.rectangle_command.RectangleCommand(self.glcanvas, self.on_rectange_command_completed,
                                                                      self.camera, (ImageY, ImageX))

        if event.button() == Qt.MouseButton.MiddleButton:
            self.center_camera()

    def on_mouse_drag(self, event: QMouseEvent):
        (y, x) = self.getCorrectedMousePosition(event)

        if event.buttons() & Qt.MouseButton.LeftButton and self.Command is not None:
            self.Command.on_mouse_drag(event)

        if self.LastMousePosition is None:
            self.LastMousePosition = (y, x)
            return

        dx = x - self.LastMousePosition[nornir_imageregistration.iPoint.X]
        dy = (y - self.LastMousePosition[nornir_imageregistration.iPoint.Y])

        self.LastMousePosition = (y, x)

        ImageY, ImageX = self.camera.ImageCoordsForMouse(y, x)
        if ImageX is None:
            return

        ImageDX = (float(dx) / self.width) * self.camera.visible_world_width
        ImageDY = (float(dy) / self.height) * self.camera.visible_world_height

        if event.buttons() & Qt.MouseButton.RightButton:
            self.camera.lookat = (self.camera.y - ImageDY, self.camera.x - ImageDX)

        self.statusBar.update_status_bar(self.LastMousePosition)

        self.glcanvas.update()

    def on_mouse_scroll(self, event: QWheelEvent):
        if self.camera is None:
            return

        # QT wheel events use delta/120 to get the number of steps
        scroll_y = event.angleDelta().y() / 120.0

        # Check for command key (Control in QT)
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
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

        self.glcanvas.update()

    def on_rectange_command_completed(self, RectangleCommand):
        self.Command = None
        return
