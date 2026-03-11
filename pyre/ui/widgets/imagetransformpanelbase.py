"""
Created on Feb 6, 2015

@author: u0490822
"""
from abc import abstractmethod

import PyQt6.QtOpenGLWidgets
import numpy as np
from PyQt6.QtWidgets import QWidget, QVBoxLayout
from PyQt6.QtCore import Qt, QSize, QPoint, pyqtSignal, QTimer
from PyQt6.QtGui import QResizeEvent, QMouseEvent

from pyre.interfaces.managers import IGLContextManager

from dependency_injector.wiring import Provide, inject
import nornir_imageregistration
from pyre.ui import Camera
from pyre.ui.widgets import glpanel
from pyre.ui.widgets.camerastatusbar import CameraStatusBar
from pyre.controllers.transformcontroller import TransformController
from pyre.container import IContainer


class ImageTransformPanelBase(PyQt6.QtOpenGLWidgets.QOpenGLWidget):
    """
    Contains a GLContext and a camera to render a scene
    """
    _camera: Camera
    _glpanel: glpanel.GLPanel
    # _width: int
    # _height: int
    _statusbar: CameraStatusBar
    _transform_controller: TransformController

    _glcontextmanager: IGLContextManager = Provide[IContainer.glcontext_manager]

    # Signal for camera changes
    camera_changed = pyqtSignal()

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
            self._camera.RemoveOnChangeEventListener(self.onCameraChanged)

        self._camera = value

        if value is not None:
            assert (isinstance(value, Camera))
            value.AddOnChangeEventListener(self.onCameraChanged)

    @property
    def glcanvas(self):
        """Alias for _glpanel for backwards compatibility"""
        return self._glpanel

    @property
    def transform_controller(self) -> TransformController:
        return self._transform_controller

    #
    # @property
    # def width(self) -> int:
    #     """Width of the image in pixels"""
    #     return self._width
    #
    # @property
    # def height(self) -> int:
    #     """Height of the image in pixels"""
    #     return self._height

    @inject
    def __init__(self,
                 parent: QWidget,
                 transform_controller: TransformController,
                 **kwargs):
        """
        Constructor
        """
        super().__init__(parent, **kwargs)
        self._parent = parent
        self._transform_controller = transform_controller

        # Create the OpenGL panel
        self._glpanel = glpanel.GLPanel(parent=self,
                                        draw_method=self.draw)
        # Need mouse move events without a button pressed for cursor updates and hit-testing over control points
        self._glpanel.setMouseTracking(True)

        # Create layout
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.addWidget(self._glpanel, 1)

        # Initialize camera
        self._camera = Camera((0, 0), 1)

        # Connect resize event
        self.resizeEvent = self.on_resize

        # Get initial size
        # self._width, self._height = self._glpanel.width(), self._glpanel.height()

        # Add status bar
        self.addStatusBar()

        # Connect camera change event
        self._camera.AddOnChangeEventListener(self.onCameraChanged)

        # Set focus policy to accept keyboard input
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Connect mouse enter event
        self._glpanel.enterEvent = self.on_mouse_enter

    def on_mouse_enter(self, event):
        """Handle mouse enter event"""
        self._parent.setFocus()

    def addStatusBar(self):
        """Add a status bar to the panel"""
        self._statusbar = CameraStatusBar(self,
                                          self.camera,
                                          self.glcanvas)
        self.layout.addWidget(self._statusbar)

    def __str__(self, *args, **kwargs):
        return self.window().windowTitle()

    def imageCoordsForMouse(self, y: float, x) -> tuple[float, float]:
        """Convert mouse coordinates to image coordinates"""
        return self.camera.ImageCoordsForMouse(y, x)

    def on_resize(self, event: QResizeEvent):
        """Handle resize event. Defer update_size so layout has resized _glpanel first."""
        QTimer.singleShot(0, self.update_size)

    def update_size(self):
        """Update the size of the camera and the camera's view of the world"""
        _width, _height = self._glpanel.width(), self._glpanel.height()
        # #region agent log
        try:
            import json
            import time
            from pathlib import Path
            _logpath = Path(__file__).resolve().parent.parent.parent.parent / "debug-f136c0.log"
            with open(_logpath, "a", encoding="utf-8") as _f:
                _f.write(json.dumps({"sessionId": "f136c0", "hypothesisId": "resize", "location": "imagetransformpanelbase.update_size", "message": "glpanel size", "data": {"w": _width, "h": _height}, "timestamp": int(time.time() * 1000)}) + "\n")
        except Exception:
            pass
        # #endregion
        if self.camera is not None and _width > 0 and _height > 0:
            self.camera.window_size = np.array((_height, _width))
            self.camera.focus(_width, _height)

    def getCorrectedMousePosition(self, event: QMouseEvent) -> tuple[float, float]:
        """QT uses a different coordinate system, flip the Y coordinate"""
        x, y = event.position().x(), event.position().y()
        return self.height() - y, x

    def onTransformChanged(self):
        """Handle transform changes"""
        self._glpanel.update()

    def onCameraChanged(self):
        """Handle camera changes"""
        self._glpanel.update()
        self.camera_changed.emit()

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

    @abstractmethod
    def draw(self):
        """Draw the image in either source (fixed) or target (warped) space"""
        raise NotImplementedError()
