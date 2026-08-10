import concurrent.futures
from dataclasses import dataclass
import logging
import os
import warnings

logger = logging.getLogger(__name__)

import numpy
import numpy as np
from numpy.typing import NDArray
from PyQt6.QtWidgets import QMainWindow, QMessageBox

from nornir_imageregistration import StosFile
import nornir_imageregistration.transforms
import nornir_pools
import pyre
from pyre.interfaces.managers import IImageLoader, IImageManager, IImageViewModelManager, IGLContextManager, \
    IMousePositionHistoryManager, ITransformControllerGLBufferManager, \
    IWindowManager
from pyre.state.events import ImageChangedCallback, StateEventsImpl, TransformControllerChangedCallback
from pyre.viewmodels import ImageViewModel
from pyre.controllers.transformcontroller import TransformController
from pyre.interfaces.viewtype import ViewType


@dataclass
class StosWindowConfig:
    """Configuration for a window to display/edit a single transform and source+target space images"""
    glcontext_manager: IGLContextManager
    transform_controller: TransformController
    transformglbuffer_manager: ITransformControllerGLBufferManager
    image_viewmodel_manager: IImageViewModelManager
    window_manager: IWindowManager
    image_loader: IImageLoader
    mouse_position_history_manager: IMousePositionHistoryManager


def _warn_rgb_like_paths_converted(path_display: str, *, main_color: bool, mask_color: bool) -> None:
    if not main_color and not mask_color:
        return
    bits: list[str] = []
    if main_color:
        bits.append("The main image has RGB or RGBA channels.")
    if mask_color:
        bits.append("The mask has RGB or RGBA channels.")
    QMessageBox.warning(
        None,
        "Color data converted to grayscale",
        "\n".join(bits)
        + f"\n\n{path_display}\n\n"
          "Each was converted to a single grayscale plane using standard luminance (Rec. 601) weights.",
    )


def _warn_single_file_rgb_like_converted(path_display: str) -> None:
    QMessageBox.warning(
        None,
        "Color data converted to grayscale",
        f"This file has multiple color channels (RGB or RGBA).\n\n{path_display}\n\n"
        "It was converted to grayscale using standard luminance (Rec. 601) weights.",
    )


def LoadImage(imageFullPath: str) -> ImageViewModel | None:
    """Loads an image, prints an error and returns None if the file cannot be opened"""
    try:
        return ImageViewModel(imageFullPath)
    except IOError as e:
        if not os.path.isfile(imageFullPath):
            logger.error("Image passed to load image does not exist: %s", imageFullPath)
        else:
            logger.exception("Exception opening %s", imageFullPath)

        return None


def param_to_stosfile(input: str | StosFile) -> StosFile:
    """Return a StosFile from a path string or pass through an existing StosFile. Raises ValueError for other types."""
    if isinstance(input, str):
        return StosFile.Load(input)
    elif isinstance(input, StosFile):
        return input

    raise ValueError(f"Could not load stos file from input {input}")


class StosState(StateEventsImpl):
    # Global Variables
    ExportTileSize: tuple[int, int] = (1024, 1024)
    AlignmentTileSize: tuple[int, int] = (192, 192)
    AngleSearchStepSize: float = 3
    AngleSearchMax: float = 15
    AnglesToSearch: NDArray[np.floating] = numpy.arange(-AngleSearchMax,
                                                        stop=AngleSearchMax + AngleSearchStepSize,
                                                        step=AngleSearchStepSize,
                                                        dtype=np.float64)  # numpy.linspace(-7.5, 7.5, 11)

    _fixed_image_permutations: nornir_imageregistration.ImagePermutationHelper | None
    _warped_image_permutations: nornir_imageregistration.ImagePermutationHelper | None
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
    _image_viewmodel_manager: IImageViewModelManager
    _image_manager: IImageManager
    _image_loader: IImageLoader
    _window_manager: IWindowManager | None

    _OnTransformControllerChangeEventListeners: list[TransformControllerChangedCallback] = list()
    _OnImageChangeEventListeners: list[ImageChangedCallback] = list()

    def __init__(self, transform_controller: TransformController,
                 image_manager: IImageManager,
                 image_viewmodel_manager: IImageViewModelManager,
                 image_loader: IImageLoader,
                 window_manager: IWindowManager | None = None):
        super(StosState, self).__init__()
        self._transform_controller = transform_controller
        self._image_viewmodel_manager = image_viewmodel_manager
        self._image_manager = image_manager
        self._image_loader = image_loader
        self._window_manager = window_manager

        self._fixed_image_permutations = None  # Type : nornir_imageregistration.ImagePermutationHelper
        self._warped_image_permutations = None  # Type : nornir_imageregistration.ImagePermutationHelper
        self._TransformViewModel = None
        self._WarpedImageViewModel = None
        self._FixedImageViewModel = None
        self._FixedImageMaskViewModel = None
        self._WarpedImageMaskViewModel = None
        self._CompositeImageViewModel = None

    @property
    def window_manager(self) -> IWindowManager | None:
        """Application window manager (ViewType-keyed). None in tests or before DI wiring."""
        return self._window_manager

    def _require_window_manager(self) -> IWindowManager:
        if self._window_manager is None:
            raise RuntimeError("StosState.window_manager is not set; cannot resolve STOS windows")
        return self._window_manager

    @property
    def SourceWindow(self) -> QMainWindow:
        return self._require_window_manager()[ViewType.Source]

    @property
    def TargetWindow(self) -> QMainWindow:
        return self._require_window_manager()[ViewType.Target]

    @property
    def FixedWindow(self) -> QMainWindow:
        """Deprecated: use :attr:`SourceWindow`."""
        return self.SourceWindow

    @property
    def WarpedWindow(self) -> QMainWindow:
        """Deprecated: use :attr:`TargetWindow`."""
        return self.TargetWindow

    @property
    def CompositeWindow(self) -> QMainWindow:
        return self._require_window_manager()[ViewType.Composite]

    @property
    def TransformController(self) -> TransformController:
        """The stos transform we are editing."""
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
    def SourceImageViewModel(self) -> ImageViewModel | None:
        return self._FixedImageViewModel

    @SourceImageViewModel.setter
    def SourceImageViewModel(self, val: ImageViewModel | None):
        self._FixedImageViewModel = val
        if val is not None:
            assert (isinstance(val, ImageViewModel))

        # self.FireOnImageChanged(pyre.Space.Source)

    @property
    def TargetImageViewModel(self) -> ImageViewModel | None:
        return self._WarpedImageViewModel

    @TargetImageViewModel.setter
    def TargetImageViewModel(self, val: ImageViewModel | None):
        self._WarpedImageViewModel = val
        if val is not None:
            assert (isinstance(val, ImageViewModel))

        self.FireOnImageChanged(pyre.Space.Target)

    @property
    def FixedImageViewModel(self) -> ImageViewModel | None:
        """Deprecated: use :attr:`SourceImageViewModel`."""
        return self.SourceImageViewModel

    @FixedImageViewModel.setter
    def FixedImageViewModel(self, val: ImageViewModel | None):
        self.SourceImageViewModel = val

    @property
    def WarpedImageViewModel(self) -> ImageViewModel | None:
        """Deprecated: use :attr:`TargetImageViewModel`."""
        return self.TargetImageViewModel

    @WarpedImageViewModel.setter
    def WarpedImageViewModel(self, val: ImageViewModel | None):
        self.TargetImageViewModel = val

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
    def FixedImages(self) -> nornir_imageregistration.ImagePermutationHelper | None:
        return self._fixed_image_permutations

    @property
    def WarpedImages(self) -> nornir_imageregistration.ImagePermutationHelper | None:
        return self._warped_image_permutations

    @property
    def Transform(self) -> nornir_imageregistration.ITransform | None:
        return self.TransformController.TransformModel

    @property
    def TransformType(self) -> nornir_imageregistration.transforms.TransformType | None:
        if self.Transform is None:
            return None
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

    def LoadSourceImage(self, ImageFileFullPath: str) -> ImageViewModel:
        """Load the source (mapped) image into the image/viewmodel managers and update STOS permutation state."""
        search_dirs = [os.path.dirname(ImageFileFullPath) or "."]
        result = self._image_loader.load_image_into_manager(
            ViewType.Source,
            ImageFileFullPath,
            None,
            search_dirs,
        )
        _warn_rgb_like_paths_converted(
            ImageFileFullPath,
            main_color=result.image_converted_from_color,
            mask_color=result.mask_converted_from_color,
        )
        vm = self._image_loader.create_image_viewmodel(load_result=result)
        self.SourceImageViewModel = vm
        # Reuse loader helper when no separate mask VM; avoid rebuilding extrema/stats.
        if self.FixedImageMaskViewModel is None:
            self._fixed_image_permutations = result.permutations
        else:
            self._fixed_image_permutations = self._update_image_permutations(
                self.SourceImageViewModel,
                self.FixedImageMaskViewModel,
            )
        self.FireOnImageChanged(pyre.Space.Source)
        return vm

    def LoadTargetImage(self, ImageFileFullPath: str) -> ImageViewModel:
        """Load the target (control) image into the image/viewmodel managers and update STOS permutation state."""
        search_dirs = [os.path.dirname(ImageFileFullPath) or "."]
        result = self._image_loader.load_image_into_manager(
            ViewType.Target,
            ImageFileFullPath,
            None,
            search_dirs,
        )
        _warn_rgb_like_paths_converted(
            ImageFileFullPath,
            main_color=result.image_converted_from_color,
            mask_color=result.mask_converted_from_color,
        )
        vm = self._image_loader.create_image_viewmodel(load_result=result)
        self.TargetImageViewModel = vm
        if self.WarpedImageMaskViewModel is None:
            self._warped_image_permutations = result.permutations
        else:
            self._warped_image_permutations = self._update_image_permutations(
                self.TargetImageViewModel,
                self.WarpedImageMaskViewModel,
            )
        return vm

    def LoadFixedImage(self, ImageFileFullPath: str) -> ImageViewModel:
        """Deprecated: use :meth:`LoadSourceImage`."""
        warnings.warn(
            "LoadFixedImage is deprecated; use LoadSourceImage",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.LoadSourceImage(ImageFileFullPath)

    def LoadWarpedImage(self, ImageFileFullPath: str) -> ImageViewModel:
        """Deprecated: use :meth:`LoadTargetImage`."""
        warnings.warn(
            "LoadWarpedImage is deprecated; use LoadTargetImage",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.LoadTargetImage(ImageFileFullPath)

    def LoadFixedMaskImage(self, ImageFileFullPath: str) -> ImageViewModel | None:
        self.FixedImageMaskViewModel = LoadImage(ImageFileFullPath)
        if (
            self.FixedImageMaskViewModel is not None
            and self.FixedImageMaskViewModel.rgb_like_converted_to_grayscale
        ):
            _warn_single_file_rgb_like_converted(ImageFileFullPath)
        self._fixed_image_permutations = self._update_image_permutations(
            self.SourceImageViewModel,
            self.FixedImageMaskViewModel,
        )
        return self.FixedImageMaskViewModel

    def LoadWarpedMaskImage(self, ImageFileFullPath: str) -> ImageViewModel | None:
        self.WarpedImageMaskViewModel = LoadImage(ImageFileFullPath)
        if (
            self.WarpedImageMaskViewModel is not None
            and self.WarpedImageMaskViewModel.rgb_like_converted_to_grayscale
        ):
            _warn_single_file_rgb_like_converted(ImageFileFullPath)
        self._warped_image_permutations = self._update_image_permutations(
            self.TargetImageViewModel,
            self.WarpedImageMaskViewModel,
        )
        return self.WarpedImageMaskViewModel

    @staticmethod
    def _update_image_permutations(img: ImageViewModel | None, mask: ImageViewModel | None) \
            -> nornir_imageregistration.ImagePermutationHelper | None:
        if img is None:
            return None
        elif mask is None:
            return nornir_imageregistration.ImagePermutationHelper(img.Image, None)
        else:
            return nornir_imageregistration.ImagePermutationHelper(img.Image, mask.Image)

    def WindowsLookAtFixedPoint(self, fixed_point, scale):
        """Force all STOS windows to the same Target-space center and scale."""

        self.SourceWindow.lookatfixedpoint(fixed_point, scale)  # type: ignore[attr-defined]
        self.TargetWindow.lookatfixedpoint(fixed_point, scale)  # type: ignore[attr-defined]
        self.CompositeWindow.lookatfixedpoint(fixed_point, scale)  # type: ignore[attr-defined]
