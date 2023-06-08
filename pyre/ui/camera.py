'''
Created on Oct 17, 2012

@author: u0490822
'''

import math

import nornir_imageregistration
import numpy
from pyglet.gl import *


def screen_to_volume(camera, point):
    camera.ImageCoordsForMouse(point)


class Camera(object):
    '''
    classdocs
    '''

    @property
    def x(self):
        '''Position in volume space'''
        return self._x
 
#     @x.setter
#     def x(self, value):
#         self._x = value)

    @property
    def y(self):
        '''Position in volume space'''
        return self._y

#     @y.setter
#     def y(self, value):
#         self._y = value
#         self._FireChangeEvent()
    
    @property
    def WindowSize(self):
        return self._window_size
    
    @WindowSize.setter
    def WindowSize(self, value):
        # print("Update window size: %d x %d" % (value[1], value[0]))
        self._window_size = numpy.array(value)
        self._aspect = float(self._window_size[nornir_imageregistration.iPoint.X]) / float(self._window_size[nornir_imageregistration.iPoint.Y])
        self._view_size = Camera._Calc_ViewSize(self.scale, self.Aspect)
        
    @property
    def Aspect(self):
        return self._aspect
        
    @property 
    def WindowWidth(self):
        return self._window_size[nornir_imageregistration.iPoint.X] 
    
    @property
    def WindowHeight(self):
        return self._window_size[nornir_imageregistration.iPoint.Y]

    @property 
    def VisibleImageWidth(self):
        return self._window_size[nornir_imageregistration.iPoint.X] * self.scale
    
    @property
    def VisibleImageHeight(self):
        return self._window_size[nornir_imageregistration.iPoint.Y] * self.scale
    
    @classmethod
    def _Calc_ViewSize(cls, scale, aspect):
        return numpy.array((scale, aspect * scale))
    
    @property
    def ViewSize(self):
        return self._view_size
      
    @property
    def ViewWidth(self):
        '''Visible volume width'''
        return self._view_size[nornir_imageregistration.iPoint.X]

    @property
    def ViewHeight(self):
        '''Visible volume height'''
        return self._view_size[nornir_imageregistration.iPoint.Y]
     
    @property
    def angle(self):
        return float(self._angle)

    @angle.setter
    def angle(self, value):
        self._angle = float(value)
        self._FireChangeEvent()

    @property
    def scale(self):
        return float(self._scale) 
    
    @scale.setter
    def scale(self, value):
        self._scale = float(value)
        self._view_size = Camera._Calc_ViewSize(self.scale, self.Aspect)
        self._FireChangeEvent()

    def ImageCoordsForMouse(self, y, x):
        ImageX = ((float(x) / self.WindowWidth) * self.ViewWidth) + (self.x - (self.ViewWidth / 2.0))
        ImageY = ((float(y) / self.WindowHeight) * self.ViewHeight) + (self.y - (self.ViewHeight / 2.0))
        return ImageY, ImageX
    
    @property
    def VisibleImageBoundingBox(self):

        (bottom, left) = self.ImageCoordsForMouse(0, 0)
        (top, right) = self.ImageCoordsForMouse(self.WindowHeight, self.WindowWidth)

        return nornir_imageregistration.Rectangle.CreateFromBounds((bottom, left, top, right))

    def __init__(self, position, scale=1, angle=0, size=None):
        '''
        :param tuple size: Size of the window the camera is within
        
        '''
        self._x, self._y = position  # centered on
        self._angle = 0  # tilt
        self._scale = scale  # zoom
        self.__OnChangeEventListeners = []
        self._aspect = None

        if size is None:
            self.WindowSize = numpy.array((480, 640))
        else:
            self.WindowSize = numpy.array(size)
 
    def AddOnChangeEventListener(self, func):
        self.__OnChangeEventListeners.append(func)

    def RemoveOnChangeEventListener(self, func):
        if func in self.__OnChangeEventListeners:
            self.__OnChangeEventListeners.remove(func)
            
    def _FireChangeEvent(self):
        for func in self.__OnChangeEventListeners:
            func()

    def lookat(self, point):
        ''':param tuple point: (y,x)
           :param float scale: scale
        '''
        self._x = point[nornir_imageregistration.iPoint.X]
        self._y = point[nornir_imageregistration.iPoint.Y]
        # self._scale = scale
        
        # print("X: %g Y: %g S: %g" % (self.x, self.y, self.scale))
         
        self._FireChangeEvent()

    def focus(self, win_width, win_height):
        
        self.WindowSize = (win_height, win_width)
        
        glViewport(0, 0, win_width, win_height)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        
        VisibleBoundingBox = self.VisibleImageBoundingBox 
         
        aspect = self.Aspect
 
        scale = self.scale / 2.0
        gluOrtho2D(-scale * aspect,  # left
                   +scale * aspect,  # right
                   -scale,  # bottom
                   +scale)  # top

        # Set modelview matrix to move, scale & rotate
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        gluLookAt(self.x, self.y, +1.0,  # camera  x,y,z
                  self.x, self.y, -1.0,  # look at x,y,z
                  math.sin(self.angle), math.cos(self.angle), 0.0)
