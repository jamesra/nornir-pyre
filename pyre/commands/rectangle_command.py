"""
Created on Feb 10, 2015

@author: u0490822
"""

import numpy
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QMouseEvent

import nornir_imageregistration.spatial
from pyre.commands.uicommandbase import UICommandBase
import pyre.views


class RectangleCommand(UICommandBase):
    '''
    The user interface to draw and size a rectangle
    '''

    @property
    def Origin(self):
        return self._origin

    @Origin.setter
    def Origin(self, value):
        self._origin = numpy.array(value)

    @property
    def Area(self):
        return self.rect.Area

    @property
    def LastMousePosition(self):
        return self._lastMousePosition

    @LastMousePosition.setter
    def LastMousePosition(self, value):
        self._lastMousePosition = numpy.array(value)

    def unsubscribe_to_parent(self):
        self._unbind_mouse_events()

    @property
    def rect(self):
        stacked = numpy.vstack((self.Origin, self.LastMousePosition))
        min_val = numpy.min(stacked, 0)
        max_val = numpy.max(stacked, 0)

        return nornir_imageregistration.spatial.Rectangle.CreateFromBounds(
            (min_val[nornir_imageregistration.spatial.iPoint.Y],
             min_val[nornir_imageregistration.spatial.iPoint.X],
             max_val[nornir_imageregistration.spatial.iPoint.Y],
             max_val[nornir_imageregistration.spatial.iPoint.X]))

    def __init__(self, parent, completed_func, camera, origin):
        '''
        Constructor 
        :param window parent: Window to subscribe to for events
        :param func completed_func: Function to call when command has completed
        :param Camera camera: Camera to use for mapping screen to volume coordinates
        :param tuple origin: Origin of rectangle
        '''

        super(RectangleCommand, self).__init__(parent, completed_func)
        self.camera = camera  # type: ignore[attr-defined]

        self.Origin = origin
        self.LastMousePosition = origin

        self._bind_mouse_events()

        print("Start Rect: %d x %d" % (
            self.Origin[nornir_imageregistration.spatial.iPoint.X],
            self.Origin[nornir_imageregistration.spatial.iPoint.Y]))

    def _bind_mouse_events(self):
        # In Qt, we'll override the parent's event handlers
        # The parent will call our methods directly
        pass

    def _unbind_mouse_events(self):
        # In Qt, we don't need to unbind events
        return

    def _update_last_mouse_position(self, e: QMouseEvent):
        '''Update the last mouse position using volume coordinates.
        :param QMouseEvent e: Qt mouse event
        :return: Volume coordinates in numpy array (Y,X)
        '''
        # Get the mouse position from the Qt event
        pos = e.pos()
        # Convert to GL coordinates (y is inverted in GL)
        y = self.parent.height() - pos.y()
        x = pos.x()

        ImageY, ImageX = self.camera.ImageCoordsForMouse(y, x)  # type: ignore[union-attr]
        self.LastMousePosition = numpy.array((ImageY, ImageX))

        return numpy.array((ImageY, ImageX))

    def on_mouse_drag(self, e):
        '''
        :param obj e: wx mouse move object
        :param tuple mouse_position: Position of the mouse on the screen, corrected for inverted Y coordinates in GL
        '''
        try:
            self._update_last_mouse_position(e)
            print("X: %g x Y: %g" % (self.LastMousePosition[nornir_imageregistration.spatial.iPoint.X],
                                     self.LastMousePosition[nornir_imageregistration.spatial.iPoint.Y]))
            self.parent.update()  # type: ignore[union-attr]
        finally:
            e.Skip()
        pass

    def on_mouse_release(self, e):
        '''
        :param obj e: wx mouse move object
        :param tuple mouse_position: Position of the mouse on the screen, corrected for inverted Y coordinates in GL
        '''
        self._update_last_mouse_position(e)
        print("X: %g x Y: %g" % (self.LastMousePosition[nornir_imageregistration.spatial.iPoint.X],
                                 self.LastMousePosition[nornir_imageregistration.spatial.iPoint.Y]))
        self.parent.update()  # type: ignore[union-attr]
        self.end_command()  # type: ignore[attr-defined]
        return

    def draw(self):
        pyre.views.DrawRectangle(self.rect, (0.5, 1.0, 1.0, 0.5))
        return
