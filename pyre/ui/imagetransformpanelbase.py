'''
Created on Feb 6, 2015

@author: u0490822
'''

import wx

import nornir_imageregistration.spatial as spatial
from pyre.ui import glpanel
import pyre.ui.camera
from pyre.ui.camerastatusbar import CameraStatusBar


class ImageTransformPanelBase(glpanel.GLPanel):
    '''
    classdocs
    ''' 
    
    @property
    def camera(self):
        return self._camera

    @camera.setter
    def camera(self, value):

        if not self._camera is None:
            self._camera.RemoveOnChangeEventListener(self.OnCameraChanged)

        self._camera = value

        if not value is None:
            assert(isinstance(value, pyre.ui.camera.Camera))
            value.AddOnChangeEventListener(self.OnCameraChanged)

    def __init__(self, parent, window_id=-1, **kwargs):
        '''
        Constructor
        '''
        self._camera = pyre.ui.camera.Camera((0, 0), 1)

        super(ImageTransformPanelBase, self).__init__(parent, window_id, **kwargs)
        
        (self.width, self.height) = self.canvas.GetSize()

        self.AddStatusBar()

        pass

    def AddStatusBar(self):
        self.statusBar = CameraStatusBar(self, self.camera)
        self.sizer.Add(self.statusBar, flag=wx.BOTTOM | wx.EXPAND)
        self.statusBar.SetFieldsCount(3)

    def __str__(self, *args, **kwargs):
        return self.TopLevelParent.Label

    def update(self, dt):
        pass

    def ImageCoordsForMouse(self, y, x):
        return self.camera.ImageCoordsForMouse(y, x)
    
    def on_resize(self, e):
        (self.width, self.height) = self.canvas.GetSize()
        if not self.camera is None:
            # try:
            self.camera.focus(self.height, self.width)
            # except:
            # pass

    def GetCorrectedMousePosition(self, e):
        '''wxPython inverts the mouse position, flip it back'''
        (x, y) = e.GetPosition()
        return (self.height - y, x)

    def OnTransformChanged(self):
        self.canvas.Refresh()

    def OnCameraChanged(self):
        self.canvas.Refresh()

    def lookatfixedpoint(self, point, scale):
        '''specify a point to look at in fixed space'''
        self.camera.lookat(point)
        self.camera.scale = scale

    def center_camera(self):
        '''Center the camera at whatever interesting thing this class displays
        '''

        raise NotImplementedError("Abstract function center_camera not implemented")

    def draw_objects(self):
        raise NotImplementedError("draw object is not implemented")
