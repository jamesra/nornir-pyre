import os
import sys

import wx

from nornir_imageregistration import Mosaic
import nornir_imageregistration.tileset
import nornir_pools
from pyre.viewmodels import ImageViewModel, TransformController
from pyre.views import ImageTransformView
from pyre.state.events import IStateEvents, StateEventsImpl


class MosaicState(StateEventsImpl):
    '''State for viewing a mosiac'''

    def FireOnMosaicChanged(self):
        for func in self._OnMosaicChangedEventListeners:
            func()

    def AddOnMosaicChangeEventListener(self, func):
        self._OnMosaicChangedEventListeners.append(func)

    @property
    def TransformControllerList(self):
        return self._TransformControllerList

    @property
    def ImageViewModelList(self):
        return self._ImageViewModelList

    @property
    def ImageTransformViewList(self):
        return self._ImageTransformViewList

    @ImageTransformViewList.setter
    def ImageTransformViewList(self, value):
        self._ImageTransformViewList = value

        self.FireOnMosaicChanged()

    @classmethod
    def GetMosaicTilePath(cls, tile_filename: str, mosaic_file_path: str, tiles_dir: str | None = None):
        '''Return the path to the tiles in the mosaic file'''
        tile_full_path = tile_filename
        if os.path.exists(tile_full_path):
            return os.path.dirname(tile_full_path)

        if not tiles_dir is None:
            tile_full_path = os.path.join(tiles_dir, tile_filename)
            if os.path.exists(tile_full_path):
                return tiles_dir

        mosaic_dir = os.path.dirname(mosaic_file_path)
        tile_full_path = os.path.join(mosaic_dir, tile_filename)
        if os.path.exists(tile_full_path):
            return mosaic_dir

        print("Unable to locate tiles in directories:")
        print("  %s" % mosaic_dir)
        if not tiles_dir is None:
            print("  %s" % tiles_dir)

        return None

    def __init__(self):
        super(MosaicState, self).__init__()

        self._TransformControllerList = []
        self._ImageViewModelList = []
        self._ImageTransformViewList = []
        self._OnMosaicChangedEventListeners = []

    def AllocateMosaicTile(self, transform, image_path: str, scalar: float):
        ivm = ImageViewModel(image_path)
        transform.ScaleFixed(scalar)
        tvm = TransformController(transform)

        self._ImageViewModelList.append(ivm)
        self._TransformControllerList.append(tvm)

        image_transform_view = ImageTransformView(ivm, transform_controller=transform)

        return image_transform_view

    def LoadMosaic(self, mosaicFullPath: str, tiles_dir: str | None = None):
        '''Return a list of image transform views for the mosaic file'''

        mosaic = Mosaic.LoadFromMosaicFile(mosaicFullPath)
        if len(mosaic.ImageToTransform) == 0:
            return None

        mosaic.TranslateToZeroOrigin()

        tiles_dir = MosaicState.GetMosaicTilePath(list(mosaic.ImageToTransform.keys())[0], mosaicFullPath, tiles_dir)
        if tiles_dir is None:
            return None

        tilesPathList = mosaic.CreateTilesPathList(tiles_dir)
        transform_scale = nornir_imageregistration.tileset.MostCommonScalar(list(mosaic.ImageToTransform.values()),
                                                                            tilesPathList)

        ImageTransformViewList = []

        z_step = 1.0 / float(len(mosaic.ImageToTransform))
        z = z_step - (z_step / 2.0)
        output_len = 0

        pools = nornir_pools.GetGlobalThreadPool()

        tasks = []
        for image_filename, transform in list(mosaic.ImageToTransform.items()):
            tile_full_path = os.path.join(tiles_dir, image_filename)

            task = pools.add_task(str(z), self.AllocateMosaicTile, transform, tile_full_path, transform_scale)
            task.z = z
            tasks.append(task)

            # image_transform_view = self.AllocateMosaicTile(transform, tile_full_path, transform_scale)
            # image_transform_view.z = z
            z += z_step
            # ImageTransformViewList.append(image_transform_view)

        wx.Yield()

        for t in tasks:
            image_transform_view = t.wait_return()
            image_transform_view.z = t.z
            ImageTransformViewList.append(image_transform_view)

            output = '%g' % (z * 100.0)

            sys.stdout.write('\b' * output_len)
            sys.stdout.write(output)

            output_len = len(output)

        self.ImageTransformViewList = ImageTransformViewList
        return ImageTransformViewList
