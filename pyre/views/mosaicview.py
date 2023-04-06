'''
Created on Feb 6, 2015

@author: u0490822
'''
from pyre.views import imagegridtransformview


class MosaicView(imagegridtransformview.ImageGridTransformView):
    '''
    classdocs
    '''

    @property
    def width(self):
        if self.FixedImageArray is None:
            return None
        return self.FixedImageArray.width

    @property
    def height(self):
        if self.FixedImageArray is None:
            return None
        return self.FixedImageArray.height

    @property
    def fixedwidth(self):
        if self.FixedImageArray is None:
            return None
        return self.FixedImageArray.width

    @property
    def fixedheight(self):
        if self.FixedImageArray is None:
            return None
        return self.FixedImageArray.height

    @property
    def Tiles(self):
        '''Collection of ImageTransformViews'''
        return self._tiles

    def AddTile(self, ID, value):
        self._tiles[ID] = value

    def __init__(self, **kwargs):
        '''
        Constructor
        '''

        self._tiles = {}
