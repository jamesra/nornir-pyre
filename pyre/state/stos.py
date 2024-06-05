import enum
import os
import numpy
import numpy as np
from numpy.typing import NDArray
from dataclasses import dataclass
import wx
from enum import Enum
import concurrent.futures

from nornir_imageregistration import StosFile
import nornir_imageregistration.transforms
from nornir_imageregistration.transforms import factory as factory
import nornir_pools
import pyre
from pyre.viewmodels import ImageViewModel, TransformController
from pyre.state.events import IStateEvents, StateEventsImpl, ImageChangedCallback, TransformControllerChangedCallback

from .image_viewmodel_manager import IImageViewModelManager
from pyre.state.gl_context_manager import IGLContextManager
from .transformcontroller_glbuffer_manager import ITransformControllerGLBufferManager
from .window_manager import IWindowManager
from .image_manager import IImageManager


@dataclass
class StosWindowConfig:
    """Configuration for a window to display/edit a single transform and source+target space images"""
    glcontext_manager: IGLContextManager
    transform_controller: TransformController
    transformglbuffer_manager: ITransformControllerGLBufferManager
    imageviewmodel_manager: IImageViewModelManager
    window_manager: IWindowManager


def LoadImage(imageFullPath: str) -> ImageViewModel | None:
    """Loads an image, prints an error and returns None if the file cannot be opened"""
    try:
        return ImageViewModel(imageFullPath)
    except IOError as e:
        if not os.path.isfile(imageFullPath):
            print("Image passed to load image does not exist: " + imageFullPath)
        else:
            print(f"Exception opening {imageFullPath}:\n{e}")

        return None


class ImageLoader:

    def __init__(self, image_manager: IImageManager,
                 imageviewmodel_manager: IImageViewModelManager,
                 ):
        self._image_manager = image_manager
        self._image_viewmodel_manager = imageviewmodel_manager

    def load_stos(self,
                  stos_path: str) -> nornir_imageregistration.ITransform:
        """Loads a stos file and the images it references."""
        obj = StosFile.Load(stos_path)
        transform = factory.LoadTransform(obj.Transform)

    def load_image_into_manager_task(
            self,
            key: str | Enum | None,
            image_path: str,
            mask_path: str | None,
            image_manager: IImageManager,
            search_dirs: list[str]) -> tuple[str, nornir_imageregistration.ImagePermutationHelper]:
        """Loads an image and optionally a mask from disk.
        :param key: The key to store the image under in the image manager. If None the key will be the base name of the image file.
        :return: A tuple with the key and the permutations object."""
        key = key if key is not None else os.path.basename(image_path)
        image_path = StosState._try_locate_file(image_path, search_dirs)
        image = nornir_imageregistration.LoadImage(image_path)
        if mask_path is not None:
            mask_path = StosState._try_locate_file(image_path, search_dirs)
            image_mask = nornir_imageregistration.LoadImage(mask_path)
        else:
            image_mask = None

        permutations = image_manager.add(key=key,
                                         image=image,
                                         mask=image_mask)
        return key, permutations

    def create_image_viewmodel(self,
                               name: str | Enum,
                               permutations: nornir_imageregistration.ImagePermutationHelper,
                               imageviewmodel_manager: IImageViewModelManager) -> ImageViewModel:
        viewmodel = ImageViewModel(permutations.Image)
        imageviewmodel_manager.add(name, viewmodel)


class StosState(StateEventsImpl):
    # Global Variables
    ExportTileSize: tuple[int, int] = (1024, 1024)
    AlignmentTileSize: tuple[int, int] = (192, 192)
    AngleSearchStepSize: float = 3
    AngleSearchMax: float = 15
    AnglesToSearch: NDArray[np.floating] = numpy.arange(start=-AngleSearchMax,
                                                        stop=AngleSearchMax + AngleSearchStepSize,
                                                        step=AngleSearchStepSize)  # numpy.linspace(-7.5, 7.5, 11)

    _fixed_image_permutations: nornir_imageregistration.ImagePermutationHelper
    _warped_image_permutations: nornir_imageregistration.ImagePermutationHelper
    _TransformViewModel = None
    _WarpedImageViewModel = None
    _FixedImageViewModel = None
    _FixedImageMaskViewModel = None
    _WarpedImageMaskViewModel = None
    _CompositeImageViewModel = None

    stosfilename: str = ''  # Path to the last stos file we loaded
    stosdirname: str = ''  # Path to last directory we loaded a stos file from

    _transform_controller: TransformController  # The transform controller for the stos transform displayed
    _transform_gl_viewmodel: pyre.viewmodels.TransformGLViewModel | None = None
    _imageview_manager: IImageViewModelManager
    _image_manager: IImageManager

    _OnTransformControllerChangeEventListeners: list[TransformControllerChangedCallback] = list()
    _OnImageChangeEventListeners: list[ImageChangedCallback] = list()

    def __init__(self, transform_controller: TransformController,
                 image_manager: IImageManager,
                 imageview_manager: IImageViewModelManager,
                 imageviewmodel_manager: IImageViewModelManager):
        super(StosState, self).__init__()
        self._transform_controller = transform_controller
        self._imageview_manager = imageview_manager

        self._fixed_image_permutations = None  # Type : nornir_imageregistration.ImagePermutationHelper
        self._warped_image_permutations = None  # Type : nornir_imageregistration.ImagePermutationHelper
        self._TransformViewModel = None
        self._WarpedImageViewModel = None
        self._FixedImageViewModel = None
        self._FixedImageMaskViewModel = None
        self._WarpedImageMaskViewModel = None
        self._CompositeImageViewModel = None

    @property
    def FixedWindow(self) -> wx.Frame:
        return pyre.Windows["Fixed"]

    @property
    def WarpedWindow(self) -> wx.Frame:
        return pyre.Windows["Warped"]

    @property
    def CompositeWindow(self) -> wx.Frame:
        return pyre.Windows["Composite"]

    @property
    def TransformController(self) -> TransformController:
        """The stos transform we are editting."""
        return self._transform_controller

    @property
    def FixedImageFullPath(self) -> str | None:
        return None if self.FixedImageViewModel is None else self.FixedImageViewModel.ImageFilename

    @property
    def WarpedImageFullPath(self) -> str | None:
        return None if self.WarpedImageViewModel is None else self.WarpedImageViewModel.ImageFilename

    @property
    def FixedImageMaskFullPath(self) -> str | None:
        return None if self.FixedImageMaskViewModel is None or self.FixedImageMaskViewModel.ImageFilename is None else self.FixedImageMaskViewModel.ImageFilename

    @property
    def WarpedImageMaskFullPath(self) -> str | None:
        return None if self.WarpedImageMaskViewModel is None or self.WarpedImageMaskViewModel.ImageFilename is None else self.WarpedImageMaskViewModel.ImageFilename

    @property
    def FixedImageViewModel(self) -> ImageViewModel | None:
        return self._FixedImageViewModel

    @FixedImageViewModel.setter
    def FixedImageViewModel(self, val: ImageViewModel | None):
        self._FixedImageViewModel = val
        if val is not None:
            assert (isinstance(val, ImageViewModel))

        # self.FireOnImageChanged(pyre.Space.Source)

    @property
    def WarpedImageViewModel(self) -> ImageViewModel | None:
        return self._WarpedImageViewModel

    @WarpedImageViewModel.setter
    def WarpedImageViewModel(self, val: ImageViewModel | None):
        self._WarpedImageViewModel = val
        if val is not None:
            assert (isinstance(val, ImageViewModel))

        self.FireOnImageChanged(pyre.Space.Target)

    @property
    def FixedImageMaskViewModel(self) -> ImageViewModel | None:
        return self._FixedImageMaskViewModel

    @FixedImageMaskViewModel.setter
    def FixedImageMaskViewModel(self, val: ImageViewModel | None):
        self._FixedImageMaskViewModel = val
        if val is not None:
            assert (isinstance(val, ImageViewModel))

        self.FireOnImageChanged(pyre.Space.Source)

    @property
    def WarpedImageMaskViewModel(self) -> ImageViewModel | None:
        return self._WarpedImageMaskViewModel

    @WarpedImageMaskViewModel.setter
    def WarpedImageMaskViewModel(self, val: ImageViewModel | None):
        self._WarpedImageMaskViewModel = val
        if val is not None:
            assert (isinstance(val, ImageViewModel))

        self.FireOnImageChanged(pyre.Space.Target)

    @property
    def CompositeImageViewModel(self):
        return self._CompositeImageViewModel

    @CompositeImageViewModel.setter
    def CompositeImageViewModel(self, val):
        self._CompositeImageViewModel = val
        if val is not None:
            assert (isinstance(val, ImageViewModel))

        self.FireOnImageChanged(pyre.Space.Source | pyre.Space.Target)

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
    def GetTransformType(
            transform: nornir_imageregistration.ITransform) -> nornir_imageregistration.transforms.TransformType:
        return transform.type

    def AddOnTransformControllerChangeEventListener(self, func: TransformControllerChangedCallback):
        self._OnTransformControllerChangeEventListeners.append(func)

    def FireOnTransformControllerChanged(self, transform_controller: TransformController):
        for func in self._OnTransformControllerChangeEventListeners:
            func(transform_controller)

    def AddOnImageViewModelChangeEventListener(self, func):
        self._OnImageChangeEventListeners.append(func)

    def FireOnImageChanged(self, image_space: pyre.Space):
        for func in self._OnImageChangeEventListeners:
            func(image_space)

    def LoadTransform(self, StosData: str | StosFile):
        """:return: A transform"""

        obj = None
        if isinstance(StosData, str):
            obj = StosFile.Load(StosData)
        elif isinstance(StosData, StosFile):
            obj = StosData

        if obj is None:
            return

        stostransform = factory.LoadTransform(obj.Transform)
        if stostransform is not None:
            self._transform_controller.TransformModel = stostransform

    #
    # def LoadFixedImage(self, ImageFileFullPath: str) -> ImageViewModel:
    #     self.FixedImageViewModel = LoadImage(ImageFileFullPath)
    #     self._fixed_image_permutations = self._update_image_permutations(self.FixedImageViewModel,
    #                                                                      self.FixedImageMaskViewModel)
    #
    # def LoadWarpedImage(self, ImageFileFullPath: str) -> ImageViewModel:
    #     self.WarpedImageViewModel = LoadImage(ImageFileFullPath)
    #     self._warped_image_permutations = self._update_image_permutations(self.WarpedImageViewModel,
    #                                                                       self.WarpedImageMaskViewModel)
    #
    # def LoadFixedMaskImage(self, ImageFileFullPath: str) -> ImageViewModel:
    #     self.FixedImageMaskViewModel = LoadImage(ImageFileFullPath)
    #     self._fixed_image_permutations = self._update_image_permutations(self.FixedImageViewModel,
    #                                                                      self.FixedImageMaskViewModel)
    #
    # def LoadWarpedMaskImage(self, ImageFileFullPath: str) -> ImageViewModel:
    #     self.WarpedImageMaskViewModel = LoadImage(ImageFileFullPath)
    #     self._warped_image_permutations = self._update_image_permutations(self.WarpedImageViewModel,
    #                                                                       self.WarpedImageMaskViewModel)

    @staticmethod
    def _update_image_permutations(img: ImageViewModel | None, mask: ImageViewModel | None) \
            -> nornir_imageregistration.ImagePermutationHelper:
        if img is None:
            return None
        elif mask is None:
            return nornir_imageregistration.ImagePermutationHelper(img.Image, None)
        else:
            return nornir_imageregistration.ImagePermutationHelper(img.Image, mask.Image)

    @staticmethod
    def _try_locate_file(ImageFullPath: str, listAltDirs: list[str]) -> str | None:
        """
        If the image path is not a file this function searches the list of directories for the image file in order.
        :returns: The full path to the image file if found, otherwise None.
        """
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

    def LoadStos2(self, stosFullPath: str | None):

        success = True

        dirname = os.path.dirname(stosFullPath)
        filename = os.path.basename(stosFullPath)

        obj = StosFile.Load(os.path.join(dirname, filename))
        self.LoadTransform(stosFullPath)

        with concurrent.futures.ThreadPoolExecutor() as pool:
            load_image_into_manager_task(obj.ControlImageFullPath, obj.ControlMaskFullPath, self._imageview_manager)

    def LoadStos(self, stosFullPath: str | None):

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
            ControlImageTask = pool.add_task('load fixed %s' % ControlImagePath, LoadImage, ControlImagePath)
        else:
            print("Could not find fixed image: " + obj.ControlImageFullPath)
            success = False

        WarpedImagePath = self._try_locate_file(obj.MappedImageFullPath, [dirname])
        if WarpedImagePath is not None:
            WarpedImageTask = pool.add_task('load warped %s' % WarpedImagePath, LoadImage, WarpedImagePath)
        else:
            print("Could not find warped image: " + obj.MappedImageFullPath)
            success = False

        if obj.HasMasks and success:
            ControlMaskImagePath = self._try_locate_file(obj.ControlMaskFullPath, [dirname])
            if ControlMaskImagePath:
                ControlImageMaskTask = pool.add_task('load fixed mask %s' % ControlMaskImagePath, LoadImage,
                                                     ControlMaskImagePath)

            WarpedMaskImagePath = self._try_locate_file(obj.MappedMaskFullPath, [dirname])
            if WarpedMaskImagePath:
                WarpedImageMaskTask = pool.add_task('load warped mask %s' % WarpedMaskImagePath, LoadImage,
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
        """Force all open windows to look at this point"""

        self.FixedWindow.lookatfixedpoint(fixed_point, scale)
        self.WarpedWindow.lookatfixedpoint(fixed_point, scale)
        self.CompositeWindow.lookatfixedpoint(fixed_point, scale)
