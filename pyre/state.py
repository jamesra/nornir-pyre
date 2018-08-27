'''
Created on Oct 24, 2012

@author: u0490822
'''
import os
import sys

from nornir_imageregistration.files.stosfile import StosFile
from nornir_imageregistration.mosaic import Mosaic
import nornir_imageregistration.tileset 
import nornir_imageregistration.transforms.factory as factory
import nornir_pools
import numpy
import wx

from pyre import Windows
from pyre.viewmodels import ImageViewModel, TransformController
from pyre.views import ImageGridTransformView
 
currentStosConfig = None
currentMosaicConfig = None


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
    def GetMosaicTilePath(cls, tile_filename, mosaic_file_path, tiles_dir=None):
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
    
    def AllocateMosaicTile(self, transform, image_path, scalar):
        ivm = ImageViewModel(image_path)
        transform.Scale(scalar)
        tvm = TransformController(transform)
        
        self._ImageViewModelList.append(ivm)
        self._TransformControllerList.append(tvm)
        
        image_transform_view = ImageGridTransformView(ivm, transform)
                
        return image_transform_view
    
    def LoadMosaic(self, mosaicFullPath, tiles_dir=None):
        '''Return a list of image transform views for the mosaic file'''
        
        mosaic = Mosaic.LoadFromMosaicFile(mosaicFullPath) 
        if len(mosaic.ImageToTransform) == 0:
            return None
        
        mosaic.TranslateToZeroOrigin()
        
        tiles_dir = MosaicState.GetMosaicTilePath(mosaic.ImageToTransform.keys()[0], mosaicFullPath, tiles_dir)
        if tiles_dir is None:
            return None
        
        tilesPathList = mosaic.CreateTilesPathList(tiles_dir)
        transform_scale = nornir_imageregistration.tileset.MostCommonScalar(mosaic.ImageToTransform.values(), tilesPathList)
        
        ImageTransformViewList = []
        
        z_step = 1.0 / float(len(mosaic.ImageToTransform))
        z = z_step - (z_step / 2.0)
        output_len = 0
        
        pools = nornir_pools.GetGlobalThreadPool()
        
        tasks = []
        for image_filename, transform in mosaic.ImageToTransform.items():
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
    ExportTileSize = [1024, 1024]

    AlignmentTileSize = [128, 128]
    AnglesToSearch = numpy.linspace(-7.5, 7.5, 11)
    
    @property
    def FixedWindow(self):
        return Windows["Fixed"]
    
    @property
    def WarpedWindow(self):
        return Windows["Warped"]
    
    @property
    def CompositeWindow(self):
        return Windows["Composite"]
    
    @property
    def FixedImageFullPath(self):
        return self.fixedImageViewModel.ImageFilename

    @property
    def WarpedImageFullPath(self):
        return self.warpedImageViewModel.ImageFilename

    @property
    def FixedImageViewModel(self):
        return self._FixedImageViewModel

    @FixedImageViewModel.setter
    def FixedImageViewModel(self, val):
        self._FixedImageViewModel = val
        if not val is None:
            assert(isinstance(val, ImageViewModel))

        self.FireOnImageChanged(True)

    @property
    def WarpedImageViewModel(self):
        return self._WarpedImageViewModel

    @WarpedImageViewModel.setter
    def WarpedImageViewModel(self, val):
        self._WarpedImageViewModel = val
        if not val is None:
            assert(isinstance(val, ImageViewModel))

        self.FireOnImageChanged(False)

    @property
    def CompositeImageViewModel(self):
        return self._CompositeImageViewModel

    @CompositeImageViewModel.setter
    def CompositeImageViewModel(self, val):
        self._CompositeImageViewModel = val
        if not val is None:
            assert(isinstance(val, ImageViewModel))

        self.FireOnImageChanged(False)
        
    @property
    def Transform(self):
        return self.TransformController.TransformModel

    @property
    def TransformController(self):
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
    def TransformController(self, val):
        self._TransformViewModel = val

        if not val is None:
            assert(isinstance(val, TransformController))

        self.FireOnTransformControllerChanged()

    def __init__(self):

        self._TransformViewModel = None
        self._WarpedImageViewModel = None
        self._FixedImageViewModel = None
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
        if not stostransform is None:
            self.TransformController.SetPoints(stostransform.points)

    def LoadFixedImage(self, ImageFileFullPath):
        self.LoadImage(ImageFileFullPath, FixedImage=True)

    def LoadWarpedImage(self, ImageFileFullPath):
        self.LoadImage(ImageFileFullPath, FixedImage=False)

    def LoadImage(self, imageFullPath, FixedImage=True):

        if not os.path.exists(imageFullPath):
            print("Image passed to load image does not exist: " + imageFullPath)
            return

        ivm = ImageViewModel(imageFullPath)
        if FixedImage:
            self.FixedImageViewModel = ivm
        else:
            self.WarpedImageViewModel = ivm

    def LoadStos(self, stosFullPath):

        if stosFullPath is None:
            return False

        success = True

        dirname = os.path.dirname(stosFullPath)
        filename = os.path.basename(stosFullPath)

        obj = StosFile.Load(os.path.join(dirname, filename))
        self.LoadTransform(stosFullPath)

        if os.path.exists(obj.ControlImageFullPath):
            self.LoadFixedImage(obj.ControlImageFullPath)
        else:
            nextPath = os.path.join(dirname, obj.ControlImageName)
            if os.path.exists(nextPath):
                self.LoadFixedImage(nextPath)
            else:
                print("Could not find fixed image: " + obj.ControlImageFullPath)
                success = False

        if os.path.exists(obj.MappedImageFullPath):
            self.LoadWarpedImage(obj.MappedImageFullPath)
        else:
            nextPath = os.path.join(dirname, obj.MappedImageName)
            if os.path.exists(nextPath):
                self.LoadWarpedImage(nextPath)
            else:
                print("Could not find fixed image: " + obj.MappedImageFullPath)
                success = False

        return success

    def WindowsLookAtFixedPoint(self, fixed_point, scale):
        '''Force all open windows to look at this point'''

        self.FixedWindow.lookatfixedpoint(fixed_point, scale)
        self.WarpedWindow.lookatfixedpoint(fixed_point, scale)
        self.CompositeWindow.lookatfixedpoint(fixed_point, scale)


def init(): 
    global currentStosConfig
    currentStosConfig = StosState()

    global currentMosaicConfig 
    currentMosaicConfig = MosaicState()
