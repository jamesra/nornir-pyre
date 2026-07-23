'''
Created on Feb 6, 2015

@author: u0490822
'''

import math

import nornir_imageregistration
import nornir_imageregistration.spatial
import pyre.state as state

from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QPoint, pyqtSignal
from PyQt6.QtGui import QWheelEvent, QMouseEvent, QKeyEvent

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

        mosaic_config = state.get_current_mosaic_config()
        if mosaic_config is not None:
            mosaic_config.AddOnMosaicChangeEventListener(self.OnMosaicChanged)
        self._imageTransformViewList = imageTransformViewList

        self.LastMousePosition = None

        self._bind_mouse_events()

        self.addStatusBar()

    def on_mouse_enter(self, event):
        """Keep focus on the mosaic panel so WASD / Page Up–Down reach keyPressEvent."""
        self.setFocus()

    def keyPressEvent(self, event: QKeyEvent):
        if self.camera is None:
            super().keyPressEvent(event)
            return
        keycode = event.key()
        symbol = ''
        if 32 <= int(keycode) <= 126:
            symbol = chr(int(keycode)).lower()
        handled = False
        if symbol == 'a':
            self.camera.translate((0.0, -0.05 * self.camera.visible_world_width))  # type: ignore[union-attr]
            handled = True
        elif symbol == 'd':
            self.camera.translate((0.0, 0.05 * self.camera.visible_world_width))  # type: ignore[union-attr]
            handled = True
        elif symbol == 'w':
            self.camera.translate((0.05 * self.camera.visible_world_height, 0))  # type: ignore[union-attr]
            handled = True
        elif symbol == 's':
            self.camera.translate((-0.05 * self.camera.visible_world_height, 0))  # type: ignore[union-attr]
            handled = True
        elif keycode == Qt.Key.Key_PageUp:
            self.camera.scale *= 0.9  # type: ignore[union-attr]
            handled = True
        elif keycode == Qt.Key.Key_PageDown:
            self.camera.scale *= 1.1  # type: ignore[union-attr]
            handled = True
        if handled:
            self.statusBar.update_status_bar(self.LastMousePosition)  # type: ignore[union-attr]
            self.glcanvas.update()
            event.accept()
        else:
            super().keyPressEvent(event)

    def OnMosaicChanged(self):
        mosaic_config = state.get_current_mosaic_config()
        if mosaic_config is not None:
            self.ImageTransformViewList = mosaic_config.ImageTransformViewList
        self.center_camera()

    def _bind_mouse_events(self):
        # Connect mouse events to the glcanvas
        self.glcanvas.wheelEvent = self.on_mouse_scroll  # type: ignore[method-assign]
        self.glcanvas.mouseMoveEvent = self.on_mouse_drag  # type: ignore[method-assign]
        self.glcanvas.mousePressEvent = self.on_mouse_press  # type: ignore[method-assign]

    def addStatusBar(self):
        self.statusBar = pyre.ui.widgets.camerastatusbar.CameraStatusBar(self,  # type: ignore[attr-defined]
                                                                         self.camera,
                                                                         self.glcanvas)
        self._layout.addWidget(self.statusBar)  # type: ignore[union-attr]

    def center_camera(self):
        '''Center the camera at whatever interesting thing this class displays
        '''
        transforms = _get_transforms(self.ImageTransformViewList)
        bbox = utils.FixedBoundingBox(transforms)
        bbox_rect = nornir_imageregistration.spatial.Rectangle.CreateFromBounds(bbox)  # type: ignore[arg-type]
        self.camera.lookat = bbox_rect.Center  # type: ignore[union-attr]
        self.camera.scale = bbox_rect.Width  # type: ignore[union-attr]

    def draw(self):
        self.camera.focus(self.width(), self.height())  # type: ignore[union-attr]

        pointScale = self.camera.scale / self.height()  # type: ignore[union-attr]

        pyre.views.SetDrawMosaicState()  # type: ignore[call-arg]

        bounding_box = self.camera.VisibleImageBoundingBox  # type: ignore[union-attr]

        for itv in self.ImageTransformViewList:
            itv.draw(ShowWarped=True, bounding_box=bounding_box, glFunc=gl.GL_FUNC_ADD)

        pyre.views.ClearDrawTextureState()  # type: ignore[call-arg]

        for itv in self.ImageTransformViewList:
            itv.draw_points(SelectedIndex=None, BoundingBox=self.camera.VisibleImageBoundingBox, FixedSpace=True,  # type: ignore[union-attr]
                            ScaleFactor=pointScale)

    def on_mouse_press(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.MiddleButton:
            self.center_camera()

    def on_mouse_drag(self, event: QMouseEvent):
        (y, x) = self.getCorrectedMousePosition(event)

        if self.LastMousePosition is None:
            self.LastMousePosition = (y, x)
            return

        dx = x - self.LastMousePosition[nornir_imageregistration.iPoint.X]
        dy = (y - self.LastMousePosition[nornir_imageregistration.iPoint.Y])

        self.LastMousePosition = (y, x)

        if event.buttons() & Qt.MouseButton.RightButton:
            self.camera.pan_by_screen_delta(dx, dy, self.width(), self.height())  # type: ignore[union-attr]

        self.statusBar.update_status_bar(self.LastMousePosition)

        self.glcanvas.update()

    def on_mouse_scroll(self, event: QWheelEvent):
        if self.camera is None:
            return

        # QT wheel events use delta/120 to get the number of steps
        scroll_y = event.angleDelta().y() / 120.0

        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            angle = float(abs(scroll_y) * 2) ** 2.0
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                angle = float(abs(scroll_y) / 2) ** 2.0
            rangle = (angle / 180.0) * math.pi
            if scroll_y < 0:
                rangle = -rangle
            try:
                height = self.glcanvas.height()
                width = self.glcanvas.width()
                center_y, center_x = height / 2.0, width / 2.0
                world_center = self.camera.ImageCoordsForMouse(center_y, center_x)  # type: ignore[union-attr]
                self.transform_controller.Rotate(rangle, world_center)
            except NotImplementedError:
                pass
        else:
            zdelta = (1 + (scroll_y / 40.0))
            self.camera.scale *= zdelta  # type: ignore[union-attr]

        self.statusBar.update_status_bar(self.LastMousePosition)

        self.glcanvas.update()
