'''
Created on Feb 6, 2015

@author: u0490822
'''
from pyre.views import imagetransformview


class MosaicView(imagetransformview.ImageTransformView):
    '''
    classdocs
    '''

    @property
    def width(self):
        fixed = self.FixedImageArray  # type: ignore[attr-defined]
        if fixed is None:
            return None
        return fixed.width

    @property
    def height(self):
        fixed = self.FixedImageArray  # type: ignore[attr-defined]
        if fixed is None:
            return None
        return fixed.height

    @property
    def fixedwidth(self):
        fixed = self.FixedImageArray  # type: ignore[attr-defined]
        if fixed is None:
            return None
        return fixed.width

    @property
    def fixedheight(self):
        fixed = self.FixedImageArray  # type: ignore[attr-defined]
        if fixed is None:
            return None
        return fixed.height

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
        super(imagetransformview.ImageTransformView, self).__init__()
        self._tiles = {}
