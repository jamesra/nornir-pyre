'''
Created on Oct 26, 2012

@author: u0490822
'''

from PIL import Image as PILImage
import numpy
import OpenGL.GL as gl
from typing import cast

from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtCore import Qt, QSize, QPoint
from PyQt6.QtGui import QOpenGLContext

from pyre.ui import Camera


class TileExportWindow(QOpenGLWidget):
    '''
    A Qt widget for exporting tiles from OpenGL views
    '''

    def __init__(self, parent=None, **kwargs):
        '''
        Constructor
        '''
        super(TileExportWindow, self).__init__(parent=parent, **kwargs)
        self.setVisible(False)
        self._tile_width: int = 0
        self._tile_height: int = 0
        self.camera = None

    def FetchTile(self, View, LookAt, ShowWarped, Filename, Tilesize=None, Scale=None):
        '''
        Render a view to an image buffer and save it to a file
        '''
        if Tilesize is None:
            Tilesize = [256, 256]

        if Scale is None:
            Scale = Tilesize[0] / 2

        self.makeCurrent()  # Equivalent to switch_to()

        self._tile_width = Tilesize[0]
        self._tile_height = Tilesize[1]
        self.resize(self._tile_width, self._tile_height)

        self.camera = Camera(position=LookAt, scale=Scale)

        boundingBox = self.VisibleImageBoundingBox()

        self.clear()
        self.camera.focus(self._tile_width, self._tile_height)

        View.draw(bounding_box=boundingBox, ShowWarped=ShowWarped)

        # Read pixels directly from the OpenGL buffer
        buffer = gl.glReadPixels(0, 0, self._tile_width, self._tile_height, gl.GL_RGB, gl.GL_UNSIGNED_BYTE)

        # Convert buffer to numpy array
        rawData = numpy.frombuffer(cast(bytes, buffer), dtype=numpy.uint8)
        rawData = rawData.reshape((self._tile_height, self._tile_width, 3))

        # OpenGL returns the image upside down, so flip it
        rawData = numpy.flipud(rawData)

        # Extract the red channel (assuming this is what the original code was doing)
        rawData = rawData[:, :, 0]

        if Filename is not None:
            im = PILImage.fromarray(rawData)
            im.save(Filename)

        # Normalize to 0-1 range
        rawData = rawData.astype(numpy.float32) / 255.0

        return rawData

    def clear(self):
        '''
        Clear the OpenGL buffer
        '''
        gl.glClearDepthf(1)
        gl.glClearColor(0, 0.1, 0, 1)
        gl.glClear(int(gl.GL_COLOR_BUFFER_BIT) | int(gl.GL_DEPTH_BUFFER_BIT))

    def ImageCoordsForMouse(self, x, y):
        '''
        Convert mouse coordinates to image coordinates
        '''
        assert self.camera is not None
        ImageX = ((float(x) / self._tile_width) * self.camera.visible_world_width) + (
                self.camera.x - (self.camera.visible_world_width / 2))
        ImageY = ((float(y) / self._tile_height) * self.camera.visible_world_height) + (
                self.camera.y - (self.camera.visible_world_height / 2))
        return ImageX, ImageY

    def VisibleImageBoundingBox(self):
        '''
        Calculate the bounding box of the visible area
        '''
        (left, bottom) = self.ImageCoordsForMouse(0, 0)
        (right, top) = self.ImageCoordsForMouse(self._tile_width, self._tile_height)

        return [bottom, left, top, right]
