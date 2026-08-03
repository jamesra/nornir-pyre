"""
Created on Oct 17, 2012

@author: u0490822
"""

import logging
import math
import sys
from typing import Generator, cast

import OpenGL.GL as gl
import numpy as np
from numpy.typing import NDArray
import scipy.ndimage

import nornir_imageregistration
from nornir_imageregistration.core._core import RgbLikeToGrayscaleLuminance
from nornir_shared.mathhelper import NearestPowerOfTwo
import pyre.gl_engine as gl_engine
from pyre.gl_engine.helpers import check_for_error, raise_on_error
from pyre.perf_debug import timed

Logger = logging.getLogger("ImageArray")


class ImageViewModel:
    """
    Represents a numpy image as an array of GL textures.  Read-only.
    """

    _TextureSize: NDArray[np.integer]
    _Image: NDArray[np.floating]
    _ImageArray: list[list[int]] | None = None
    _NumCols: int
    _NumRows: int
    _height: int
    _width: int
    _ImageFilename: str | None = None
    _image_stats: nornir_imageregistration.ImageStats | None
    RawImageSize: NDArray[np.integer]
    _rgb_like_converted_to_grayscale: bool
    _managed_by_filepath_cache: bool = False

    # The largest dimension we allow a texture to have
    MaxTextureDimension: int = int(4096)

    @property
    def Image(self) -> NDArray[np.floating]:
        return self._Image

    @property
    def Stats(self) -> nornir_imageregistration.ImageStats:
        """Image statistics; computed lazily on first access."""
        if self._image_stats is None:
            self._image_stats = nornir_imageregistration.ImageStats.Create(self._Image)
        return self._image_stats

    @property
    def rgb_like_converted_to_grayscale(self) -> bool:
        """True if the image had RGB/RGBA (or LA) layout and was reduced to one plane via luminance."""
        return self._rgb_like_converted_to_grayscale

    @property
    def width(self) -> int:
        """Raw image width in pixels (unpadded)."""
        return self._Image.shape[1]

    @property
    def height(self) -> int:
        """Raw image height in pixels (unpadded)."""
        return self._Image.shape[0]

    @property
    def NumRows(self) -> int:
        """Number of texture rows for the whole image"""
        return self._NumRows

    @property
    def NumCols(self) -> int:
        """Number of texture columns for the whole image"""
        return self._NumCols

    @property
    def size(self) -> tuple[int, int]:
        """Padded texture-grid size (height, width) in pixels."""
        return self._height, self._width

    @property
    def shape(self) -> tuple[int, int]:
        """Padded texture-grid shape (height, width); same as :attr:`size`."""
        return self._height, self._width

    @property
    def ImageArray(self) -> list[list[int]]:
        """Array of textures for the full image"""
        if self._ImageArray is None:
            try:
                self._ImageArray = self.CreateImageArray()
            except RuntimeError as e:
                if "No valid OpenGL context" in str(e):
                    # Context not ready yet - return empty array
                    # Textures will be created when context becomes available
                    self._ImageArray = []
                    return []
                raise
        # If ImageArray was set to empty list due to context not being ready, try again
        if self._ImageArray == []:
            try:
                self._ImageArray = self.CreateImageArray()
            except RuntimeError as e:
                if "No valid OpenGL context" in str(e):
                    # Still not ready
                    return []
                raise
        return self._ImageArray

    @property
    def TextureSize(self) -> NDArray[np.integer]:
        """Size of a texture"""
        return self._TextureSize

    @property
    def ImageFilename(self) -> str | None:
        """Filename we loaded"""
        return self._ImageFilename

    @classmethod
    def FindTextureSize(cls, shape: NDArray) -> NDArray[np.integer]:
        _TextureSize = NearestPowerOfTwo(shape)

        if _TextureSize[0] > cls.MaxTextureDimension:
            _TextureSize[0] = cls.MaxTextureDimension

        if _TextureSize[1] > cls.MaxTextureDimension:
            _TextureSize[1] = cls.MaxTextureDimension

        return _TextureSize

    def __init__(
            self,
            input_image: str | NDArray,
            image_filename: str | None = None,
            managed_by_filepath_cache: bool = False,
    ):
        """
        Constructor, _Image is either path to file or a numpy array
        """

        '''Convert the passed _Image to a Luminance Texture, cutting the image into smaller images as necessary'''
        self._managed_by_filepath_cache = managed_by_filepath_cache
        # Accept CuPy arrays from image loader (convert to numpy for viewmodel/tiling)
        get_fn = getattr(input_image, "get", None)
        if callable(get_fn):
            input_image = cast(str | NDArray, get_fn())
        if isinstance(input_image, str):

            Logger.info("Loading image: " + input_image)
            self._ImageFilename = input_image

            self._Image = nornir_imageregistration.LoadImage(input_image, dtype=np.float16) * 255  # //

            self._Image, self._rgb_like_converted_to_grayscale = RgbLikeToGrayscaleLuminance(self._Image)
            Logger.info("Loading done")
        elif isinstance(input_image, np.ndarray):
            self._Image, self._rgb_like_converted_to_grayscale = RgbLikeToGrayscaleLuminance(input_image)
            if image_filename is not None:
                self._ImageFilename = image_filename
        else:
            raise TypeError("Expected a path to an image file or a numpy ndarray")

        # Defer full-image stats until registration or other callers need them.
        self._image_stats = None

        # Images are read only, create a memory mapped file for the image for use with multithreading
        # self._Image = core.npArrayToReadOnlySharedArray(self._Image)

        self.RawImageSize = np.array(self._Image.shape)

        self._TextureSize = ImageViewModel.FindTextureSize(self.RawImageSize)
        self._NumCols = int(math.ceil(self._Image.shape[1] / float(self.TextureSize[1])))
        self._NumRows = int(math.ceil(self._Image.shape[0] / float(self.TextureSize[0])))

        self._height, self._width = self.NumRows * self.TextureSize[nornir_imageregistration.iPoint.Y], self.NumCols * \
                                    self.TextureSize[nornir_imageregistration.iPoint.X]

    def ResizeToPowerOfTwo(self, InputImage: str, tilesize: nornir_imageregistration.ShapeLike | None = None) -> \
            NDArray[np.floating]:
        if tilesize is None:
            tilesize = self.TextureSize

        tile_height = int(tilesize[0])
        tile_width = int(tilesize[1])
        Resize = nornir_imageregistration.LoadImage(InputImage, dtype=np.float32)

        height = Resize.shape[0]
        width = Resize.shape[1]

        NumCols = math.ceil(width / float(tile_width))
        NumRows = math.ceil(height / float(tile_height))

        newwidth = NumCols * tile_height
        newheight = NumRows * tile_width

        newImage = np.zeros((int(newheight), int(newwidth)), dtype=Resize.dtype)

        newImage[0:Resize.shape[0], 0:Resize.shape[1]] = Resize

        return newImage

    def CreateImageArray(self) -> list[list[int]]:
        """
        Generate an array of textures when images are larger than the max texture size
        Texture ID's in OpenGL are integers
        """
        # from Pools import Threadpool

        Logger.info("CreateImageArray")
        # Round up size to nearest power of 2

        with timed(
            f'CreateImageArray {self.ImageFilename or "array"} '
            f'{self.NumCols}x{self.NumRows} tiles'
        ):
            texture_grid = list()  # type: list[list[int]]

            for iX in range(0, self.width, self.TextureSize[nornir_imageregistration.iPoint.X]):
                columnTextures = list()  # type: list[int]
                lastCol = iX + self.TextureSize[nornir_imageregistration.iPoint.X] > self.width

                end_iX = iX + self.TextureSize[nornir_imageregistration.iPoint.X]
                pad_image = end_iX > self.Image.shape[1]
                if pad_image:
                    end_iX = self.Image.shape[1]

                for iY in range(0, self.height, self.TextureSize[nornir_imageregistration.iPoint.Y]):
                    lastRow = iY + self.TextureSize[nornir_imageregistration.iPoint.Y] > self.height

                    end_iY = iY + self.TextureSize[nornir_imageregistration.iPoint.Y]
                    if end_iY > self.Image.shape[0]:
                        end_iY = self.Image.shape[0]
                        pad_image = True

                    # temp = _Image[iX:iX + self.TextureSize[0], iY:iY + self.TextureSize[1]]

                    # if not lastRow:

                    temp = None
                    if pad_image:
                        paddedImage = np.zeros(self.TextureSize)
                        paddedImage[0:end_iY - iY, 0:end_iX - iX] = self.Image[iY:end_iY, iX:end_iX]
                        temp = paddedImage
                    else:
                        temp = self.Image[iY:end_iY, iX:end_iX]

                    try:
                        texture_input = cast(NDArray[np.uint8], nornir_imageregistration.image_to_uint8(temp))
                        texture = gl_engine.textures.create_grayscale_texture(texture_input)
                        del temp
                        columnTextures.append(texture)
                    except RuntimeError as e:
                        if "No valid OpenGL context" in str(e):
                            # Context not ready yet - return empty array, will be created later
                            Logger.warning(
                                f"OpenGL context not available when creating textures, deferring creation: {e}")
                            return []  # Return empty array - textures will be created when context is available
                        raise

                texture_grid.append(columnTextures)

            Logger.info("Completed CreateImageArray")
            raise_on_error("after CreateImageArray")
            return texture_grid

    def generate_grid_indicies(self) -> Generator[tuple[int, int], None, None]:
        """Yields all of the grid indices that cover the image"""
        for ix in range(0, self.NumCols):
            for iy in range(0, self.NumRows):
                yield ix, iy

    def is_valid_index(self, ix: int, iy: int) -> bool:
        """Returns True if the grid index is within the image grid bounds"""
        return 0 <= ix < self.NumCols and 0 <= iy < self.NumRows

    @property
    def managed_by_filepath_cache(self) -> bool:
        """True when lifetime is owned by ImageLoader filepath cache (not slot delete)."""
        return self._managed_by_filepath_cache

    def mark_managed_by_filepath_cache(self) -> None:
        """Mark this viewmodel as session-cached; defer GL cleanup until explicit release."""
        self._managed_by_filepath_cache = True

    def release_gpu_resources(self) -> None:
        """Delete uploaded GL textures and clear the texture grid."""
        if self._ImageArray is None or self._ImageArray == []:
            self._ImageArray = None
            return

        textures = [texture for row in self._ImageArray for texture in row]
        if textures:
            gl.glDeleteTextures(len(textures), textures)
            check_for_error("after glDeleteTextures in ImageViewModel.release_gpu_resources")
        self._ImageArray = None

    def __del__(self):
        """Free the GL Texture array when not retained by the filepath cache."""
        if self._managed_by_filepath_cache:
            return
        self.release_gpu_resources()
