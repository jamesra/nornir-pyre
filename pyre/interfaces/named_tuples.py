from __future__ import annotations

import os
from typing import NamedTuple

import nornir_imageregistration
from nornir_imageregistration import StosFile


class ImageLoadResult(NamedTuple):
    """
    Contains the results of loading an image.
    Paths in the loaded image will contain updated paths if substitution paths were used.
    The original paths before substitution are stored in image_original_fullpath and mask_original_fullpath
    """
    key: str  # key to store the image under in the image manager
    permutations: nornir_imageregistration.ImagePermutationHelper  # Image data loaded
    image_fullpath: str  # Path to the image file
    image_original_fullpath: str  # Path to the original image file, this will be different if a path was substituted
    mask_fullpath: str | None  # Path to the mask file
    mask_original_fullpath: str | None  # Path to the original mask file, this will be different if a path was substituted

    @property
    def image_dirname(self) -> str:
        """Path to image directory containing loaded image"""
        return os.path.dirname(self.image_fullpath)

    @property
    def original_image_dirname(self) -> str:
        """Original path to image before path substition applied"""
        return os.path.dirname(self.image_original_fullpath)

    @property
    def mask_dirname(self) -> str | None:
        """Path to mask directory containing loaded mask"""
        return os.path.dirname(self.mask_fullpath)

    @property
    def original_mask_dirname(self) -> str | None:
        """Original path to mask before path substition applied"""
        return os.path.dirname(self.mask_original_fullpath)

    @property
    def image_basename(self) -> str:
        """Filename of the image.  Should not change during path substitution"""
        return os.path.basename(self.image_fullpath)

    @property
    def mask_basename(self) -> str | None:
        """Filename of the mask.  Should not change during path substitution"""
        return os.path.basename(self.mask_fullpath) if self.mask_fullpath is not None else None


class LoadStosResult(NamedTuple):
    """Result of loading a stos file.
    This contains the loaded stos file and the results of loading stos file images
    Paths in the loaded images will contain updated paths if substitution paths were used
    """
    stos: StosFile
    source: ImageLoadResult
    target: ImageLoadResult
