'''
Created on Feb 10, 2015

@author: u0490822
'''

import numpy
import wx

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

        super(RectangleCommand, self).__init__(parent, completed_func, camera)

        self.Origin = origin
        self.LastMousePosition = origin

        self._bind_mouse_events()

        print("Start Rect: %d x %d" % (
            self.Origin[nornir_imageregistration.spatial.iPoint.X],
            self.Origin[nornir_imageregistration.spatial.iPoint.Y]))

    def _bind_mouse_events(self):
        self.parent.Bind(wx.EVT_MOTION, self.on_mouse_drag)
        self.parent.Bind(wx.EVT_LEFT_UP, self.on_mouse_release)

    def _unbind_mouse_events(self):
        self.parent.Unbind(wx.EVT_MOTION, handler=self.on_mouse_drag)
        self.parent.Unbind(wx.EVT_LEFT_UP, handler=self.on_mouse_release)
        return

    def _update_last_mouse_position(self, e):
        '''Update the last mouse position using volume coordinates.
        :return: Volume coordinates in numpy array (Y,X)
        '''
        (y, x) = self.GetCorrectedMousePosition(e)
        ImageY, ImageX = self.camera.ImageCoordsForMouse(y, x)
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
            self.parent.Refresh()
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
        self.parent.Refresh()
        self.end_command()
        return

    def draw(self):
        pyre.views.DrawRectangle(self.rect, (0.5, 1.0, 1.0, 0.5))
        return
