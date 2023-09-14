'''
Created on Oct 26, 2012

@author: u0490822
'''

import PIL
import numpy
from pyglet import *

from pyre.ui import Camera


class TileExportWindow(window.Window):
    '''
    classdocs
    '''

    def __init__(self, **kwargs):
        '''
        Constructor
        '''

        super(TileExportWindow, self).__init__(visible=False, **kwargs)

    def FetchTile(self, View, LookAt, ShowWarped, Filename, Tilesize=None, Scale=None):

        if Tilesize is None:
            Tilesize = [256, 256]

        if Scale is None:
            Scale = Tilesize[0] / 2

        self.switch_to()

        self.width = Tilesize[0]
        self.height = Tilesize[1]

        self.camera = Camera(position=LookAt, scale=Scale)

        boundingBox = self.VisibleImageBoundingBox()

        self.clear()
        self.camera.focus(self.width, self.height)

        View.draw_textures(BoundingBox=boundingBox, ShowWarped=ShowWarped)

        imageBuffer = image.get_buffer_manager().get_color_buffer().get_image_data()

        # if(not Filename is None):
        #   imageBuffer.save(Filename);
        # Some sort of race condition causes no file to be written without a pause
        # Turns out it was an earlier call to flip was wiping out the buffer
        # time.sleep(0.5);

        data = imageBuffer.get_data(format=imageBuffer.format, pitch=imageBuffer.pitch)
        components = list(map(int, list(data)))

        rawData = numpy.array(components, dtype=numpy.int8)

        # The raw dat

        rawData = rawData.reshape((self.width, self.height, len(imageBuffer.format)))
        rawData = rawData[:, :, 2]

        rawData = numpy.flipud(rawData)
        # rawData = numpy.fliplr(rawData);

        if not Filename is None:
            im = PIL.Image.fromarray(numpy.uint8(rawData))
            im.save(Filename)

        rawData /= 255.0

        return rawData

    def ImageCoordsForMouse(self, x, y):
        ImageX = ((float(x) / self.width) * self.camera.ViewWidth) + (self.camera.x - (self.camera.ViewWidth / 2))
        ImageY = ((float(y) / self.height) * self.camera.ViewHeight) + (self.camera.y - (self.camera.ViewHeight / 2))
        return ImageX, ImageY

    def VisibleImageBoundingBox(self):

        (left, bottom) = self.ImageCoordsForMouse(0, 0)
        (right, top) = self.ImageCoordsForMouse(self.width, self.height)

        return [bottom, left, top, right]
