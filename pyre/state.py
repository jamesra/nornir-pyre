'''
Created on Oct 24, 2012

@author: u0490822
'''
import sys
import os
import numpy

import nornir_pools
from nornir_imageregistration.files.stosfile import StosFile
from nornir_imageregistration.mosaic import Mosaic
import nornir_imageregistration.tileset
import nornir_imageregistration.transforms.factory as factory

try:
    import wx
except:
    print("Ignoring wx import failure, assumed documentation use, otherwise please install wxPython")

import pyre
from pyre.viewmodels import ImageViewModel, TransformController
from pyre.views import ImageGridTransformView


def InitializeStateFromArguments(arg_values):
    if 'stosFullPath' in arg_values and arg_values.stosFullPath is not None:
        currentStosConfig.LoadStos(arg_values.stosFullPath)
    else:
        if 'WarpedImageFullPath' in arg_values and arg_values.WarpedImageFullPath is not None:
            currentStosConfig.LoadWarpedImage(arg_values.WarpedImageFullPath)
        if 'FixedImageFullPath' in arg_values and arg_values.FixedImageFullPath is not None:
            currentStosConfig.LoadFixedImage(arg_values.FixedImageFullPath)

    if 'mosaicFullPath' in arg_values and arg_values.mosaicFullPath is not None:
        tiles_path = os.path.dirname(arg_values.mosaicFullPath)
        if 'mosaicTilesFullPath' in arg_values and arg_values.mosaicTilesFullPath is not None:
            tiles_path = arg_values.mosaicTilesFullPath

        currentMosaicConfig.LoadMosaic(arg_values.mosaicFullPath, tiles_path)


class StateEvents(object):

    def __init__(self):
        self._OnTransformControllerChangeEventListeners = []
        self._OnImageChangeEventListeners = []

    def AddOnTransformControllerChangeEventListener(self, func):
        self._OnTransformControllerChangeEventListeners.append(func)

    def FireOnTransformControllerChanged(self):
        for func in self._OnTransformControllerChangeEventListeners:
            func()

    def AddOnImageViewModelChangeEventListener(self, func):
        self._OnImageChangeEventListeners.append(func)

    def FireOnImageChanged(self, FixedImage):
        for func in self._OnImageChangeEventListeners:
            func(FixedImage)


class MosaicState(StateEvents):
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

        image_transform_view = ImageGridTransformView(ivm, Transform=transform)

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


class StosState(StateEvents):
    # Global Variables
    ExportTileSize = (1024, 1024)
    AlignmentTileSize = (192, 192)
    AngleSearchStepSize = 3
    AngleSearchMax = 15
    AnglesToSearch = numpy.arange(start=-AngleSearchMax, stop=AngleSearchMax + AngleSearchStepSize,
                                  step=AngleSearchStepSize)  # numpy.linspace(-7.5, 7.5, 11)

    @property
    def FixedWindow(self):
        return pyre.Windows["Fixed"]

    @property
    def WarpedWindow(self):
        return pyre.Windows["Warped"]

    @property
    def CompositeWindow(self):
        return pyre.Windows["Composite"]

    @property
    def FixedImageFullPath(self) -> str | None:
        return None if self.FixedImageViewModel is None else self.FixedImageViewModel.ImageFilename

    @property
    def WarpedImageFullPath(self) -> str | None:
        return None if self.WarpedImageViewModel is None else self.WarpedImageViewModel.ImageFilename

    @property
    def FixedImageMaskFullPath(self) -> str | None:
        return None if self.FixedImageMaskViewModel.ImageFilename is None else self.FixedImageMaskViewModel.ImageFilename

    @property
    def WarpedImageMaskFullPath(self) -> str | None:
        return None if self.WarpedImageMaskViewModel.ImageFilename is None else self.WarpedImageMaskViewModel.ImageFilename

    @property
    def FixedImageViewModel(self) -> ImageViewModel | None:
        return self._FixedImageViewModel

    @FixedImageViewModel.setter
    def FixedImageViewModel(self, val: ImageViewModel | None):
        self._FixedImageViewModel = val
        if val is not None:
            assert (isinstance(val, ImageViewModel))

        self.FireOnImageChanged(True)

    @property
    def WarpedImageViewModel(self) -> ImageViewModel | None:
        return self._WarpedImageViewModel

    @WarpedImageViewModel.setter
    def WarpedImageViewModel(self, val: ImageViewModel | None):
        self._WarpedImageViewModel = val
        if val is not None:
            assert (isinstance(val, ImageViewModel))

        self.FireOnImageChanged(False)

    @property
    def FixedImageMaskViewModel(self) -> ImageViewModel | None:
        return self._FixedImageMaskViewModel

    @FixedImageMaskViewModel.setter
    def FixedImageMaskViewModel(self, val: ImageViewModel | None):
        self._FixedImageMaskViewModel = val
        if val is not None:
            assert (isinstance(val, ImageViewModel))

        self.FireOnImageChanged(True)

    @property
    def WarpedImageMaskViewModel(self) -> ImageViewModel | None:
        return self._WarpedImageMaskViewModel

    @WarpedImageMaskViewModel.setter
    def WarpedImageMaskViewModel(self, val: ImageViewModel | None):
        self._WarpedImageMaskViewModel = val
        if val is not None:
            assert (isinstance(val, ImageViewModel))

        self.FireOnImageChanged(False)

    @property
    def CompositeImageViewModel(self):
        return self._CompositeImageViewModel

    @CompositeImageViewModel.setter
    def CompositeImageViewModel(self, val):
        self._CompositeImageViewModel = val
        if val is not None:
            assert (isinstance(val, ImageViewModel))

        self.FireOnImageChanged(False)

    @property
    def FixedImages(self) -> nornir_imageregistration.ImagePermutationHelper:
        return self._fixed_image_permutations

    @property
    def WarpedImages(self) -> nornir_imageregistration.ImagePermutationHelper:
        return self._warped_image_permutations

    @property
    def Transform(self) -> nornir_imageregistration.ITransform | None:
        return self.TransformController.TransformModel

    @property
    def TransformType(self) -> nornir_imageregistration.transforms.TransformType | None:
        return self.GetTransformType(self.Transform)

    @staticmethod
    def GetTransformType(transform: nornir_imageregistration.ITransform) -> nornir_imageregistration.transforms.TransformType:
        return transform.type

    @property
    def TransformController(self) -> TransformController:
        if self._TransformViewModel is None:
            FixedShape = None
            WarpedShape = None

            if not self.WarpedImageViewModel is None:
                WarpedShape = [self.WarpedImageViewModel.height, self.WarpedImageViewModel.width]

            if not self.FixedImageViewModel is None:
                FixedShape = [self.FixedImageViewModel.height, self.FixedImageViewModel.width]

            self.TransformController = TransformController.CreateDefault(FixedShape, WarpedShape)

        return self._TransformViewModel

    @TransformController.setter
    def TransformController(self, val: TransformController):
        self._TransformViewModel = val

        if val is not None:
            assert (isinstance(val, TransformController))

        self.FireOnTransformControllerChanged()

    def __init__(self):
        self._fixed_image_permutations = None #Type : nornir_imageregistration.ImagePermutationHelper
        self._warped_image_permutations = None #Type : nornir_imageregistration.ImagePermutationHelper
        self._TransformViewModel = None
        self._WarpedImageViewModel = None
        self._FixedImageViewModel = None
        self._FixedImageMaskViewModel = None
        self._WarpedImageMaskViewModel = None
        self._CompositeImageViewModel = None

        self._OnTransformControllerChangeEventListeners = []
        self._OnImageChangeEventListeners = []

    def AddOnTransformControllerChangeEventListener(self, func):
        self._OnTransformControllerChangeEventListeners.append(func)

    def FireOnTransformControllerChanged(self):
        for func in self._OnTransformControllerChangeEventListeners:
            func()

    def AddOnImageViewModelChangeEventListener(self, func):
        self._OnImageChangeEventListeners.append(func)

    def FireOnImageChanged(self, FixedImage):
        for func in self._OnImageChangeEventListeners:
            func(FixedImage)

    def LoadTransform(self, StosData):
        ''':return: A Transform'''

        obj = None
        if isinstance(StosData, str):
            obj = StosFile.Load(StosData)
        elif isinstance(StosData, StosFile):
            obj = StosData

        if obj is None:
            return

        stostransform = factory.LoadTransform(obj.Transform)
        if stostransform is not None:
            self.TransformController.TransformModel = stostransform

    def LoadFixedImage(self, ImageFileFullPath: str) -> ImageViewModel:
        self.FixedImageViewModel = self.LoadImage(ImageFileFullPath)
        self._fixed_image_permutations = self._update_image_permutations(self.FixedImageViewModel,
                                                                         self.FixedImageMaskViewModel)

    def LoadWarpedImage(self, ImageFileFullPath: str) -> ImageViewModel:
        self.WarpedImageViewModel = self.LoadImage(ImageFileFullPath)
        self._warped_image_permutations = self._update_image_permutations(self.WarpedImageViewModel,
                                                                          self.WarpedImageMaskViewModel)

    def LoadFixedMaskImage(self, ImageFileFullPath: str) -> ImageViewModel:
        self.FixedImageMaskViewModel = self.LoadImage(ImageFileFullPath)
        self._fixed_image_permutations = self._update_image_permutations(self.FixedImageViewModel,
                                                                         self.FixedImageMaskViewModel)

    def LoadWarpedMaskImage(self, ImageFileFullPath: str) -> ImageViewModel:
        self.WarpedImageMaskViewModel = self.LoadImage(ImageFileFullPath)
        self._warped_image_permutations = self._update_image_permutations(self.WarpedImageViewModel,
                                                                          self.WarpedImageMaskViewModel)

    @staticmethod
    def _update_image_permutations(img: ImageViewModel | None, mask: ImageViewModel | None)\
            -> nornir_imageregistration.ImagePermutationHelper:
        if img is None:
            return None
        elif mask is None:
            return nornir_imageregistration.ImagePermutationHelper(img.Image, None)
        else:
            return nornir_imageregistration.ImagePermutationHelper(img.Image, mask.Image)

    def LoadImage(self, imageFullPath) -> ImageViewModel | None:
        try:
            return ImageViewModel(imageFullPath)
        except IOError as e:
            if not os.path.isfile(imageFullPath):
                print("Image passed to load image does not exist: " + imageFullPath)
            else:
                print(f"Exception opening {imageFullPath}:\n{e}")

            return None

    def _try_locate_file(self, ImageFullPath, listAltDirs):
        '''
        '''
        if os.path.exists(ImageFullPath):
            return ImageFullPath
        else:
            filename = ImageFullPath

            # Do not use the base filename if the ImagePath is relative
            if os.path.isabs(ImageFullPath):
                filename = os.path.basename(ImageFullPath)

            for dirname in listAltDirs:
                next_path = os.path.join(dirname, filename)
                if os.path.exists(next_path):
                    return next_path

        return None

    def LoadStos(self, stosFullPath):

        if stosFullPath is None:
            return False

        success = True

        dirname = os.path.dirname(stosFullPath)
        filename = os.path.basename(stosFullPath)

        obj = StosFile.Load(os.path.join(dirname, filename))
        self.LoadTransform(stosFullPath)

        pool = nornir_pools.GetGlobalThreadPool()
        ControlImageTask = None
        WarpedImageTask = None
        ControlImageMaskTask = None
        WarpedImageMaskTask = None

        # First check the absolute path in the .stos file for images, then 
        # check relative to the .stos file's directory
        ControlImagePath = self._try_locate_file(obj.ControlImageFullPath, [dirname])
        if ControlImagePath is not None:
            ControlImageTask = pool.add_task('load fixed %s' % ControlImagePath, self.LoadImage, ControlImagePath)
        else:
            print("Could not find fixed image: " + obj.ControlImageFullPath)
            success = False

        WarpedImagePath = self._try_locate_file(obj.MappedImageFullPath, [dirname])
        if WarpedImagePath is not None:
            WarpedImageTask = pool.add_task('load warped %s' % WarpedImagePath, self.LoadImage, WarpedImagePath)
        else:
            print("Could not find warped image: " + obj.MappedImageFullPath)
            success = False

        if obj.HasMasks and success:
            ControlMaskImagePath = self._try_locate_file(obj.ControlMaskFullPath, [dirname])
            if ControlMaskImagePath:
                ControlImageMaskTask = pool.add_task('load fixed mask %s' % ControlMaskImagePath, self.LoadImage,
                                                     ControlMaskImagePath)

            WarpedMaskImagePath = self._try_locate_file(obj.MappedMaskFullPath, [dirname])
            if WarpedMaskImagePath:
                WarpedImageMaskTask = pool.add_task('load warped mask %s' % WarpedMaskImagePath, self.LoadImage,
                                                    WarpedMaskImagePath)

        if ControlImageTask is not None:
            self.FixedImageViewModel = ControlImageTask.wait_return()

        if WarpedImageTask is not None:
            self.WarpedImageViewModel = WarpedImageTask.wait_return()

        if ControlImageMaskTask is not None:
            self.FixedImageMaskViewModel = ControlImageMaskTask.wait_return()

        if WarpedImageMaskTask is not None:
            self.WarpedImageMaskViewModel = WarpedImageMaskTask.wait_return()

        self._fixed_image_permutations = self._update_image_permutations(self.FixedImageViewModel,
                                                                         self.FixedImageMaskViewModel)

        self._warped_image_permutations = self._update_image_permutations(self.WarpedImageViewModel,
                                                                          self.WarpedImageMaskViewModel)
        return success

    def WindowsLookAtFixedPoint(self, fixed_point, scale):
        '''Force all open windows to look at this point'''

        self.FixedWindow.lookatfixedpoint(fixed_point, scale)
        self.WarpedWindow.lookatfixedpoint(fixed_point, scale)
        self.CompositeWindow.lookatfixedpoint(fixed_point, scale)


currentStosConfig = None  # type: StosState
currentMosaicConfig = None  # type: MosaicState

def init():
    global currentStosConfig
    currentStosConfig = StosState()

    global currentMosaicConfig
    currentMosaicConfig = MosaicState()
