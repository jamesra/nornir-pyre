from __future__ import annotations
import os

import abc
from enum import Enum
from typing import Callable, NamedTuple

import numpy as np
from numpy.typing import NDArray

import nornir_imageregistration
from pyre.interfaces.action import Action


class ImageLoadResult(NamedTuple):
    key: str  # key to store the image under in the image manager
    permutations: nornir_imageregistration.ImagePermutationHelper  # Image data loaded
    image_fullpath: str  # Path to the image file
    mask_fullpath: str | None  # Path to the mask file

    @property
    def image_dirname(self) -> str:
        return os.path.dirname(self.image_fullpath)

    @property
    def mask_dirname(self) -> str | None:
        return os.path.dirname(self.mask_fullpath)

    @property
    def image_basename(self) -> str:
        return os.path.basename(self.image_fullpath)

    @property
    def mask_basename(self) -> str | None:
        return os.path.basename(self.mask_fullpath) if self.mask_fullpath is not None else None


class IImageLoader(abc.ABC):

    @abc.abstractmethod
    def load_stos(self, stos_path: str) -> nornir_imageregistration.ITransform:
        raise NotImplementedError()

    @abc.abstractmethod
    def load_image_into_manager(self, key: str | Enum | None,
                                image_path: str,
                                mask_path: str | None,
                                search_dirs: list[str]) -> ImageLoadResult:
        raise NotImplementedError()

    @abc.abstractmethod
    def create_image_viewmodel(self, name: str | Enum,
                               permutations: nornir_imageregistration.ImagePermutationHelper) -> "pyre.viewmodels.ImageViewModel":
        raise NotImplementedError()


# Change event for the ImageManager, passes the key and the ImagePermutationHelper associated with the key
ImageManagerChangeCallback = Callable[[Action, str, nornir_imageregistration.ImagePermutationHelper], None]


class IImageManager(abc.ABC):

    @abc.abstractmethod
    def add(self,
            key: str,
            image: str | NDArray | nornir_imageregistration.ImagePermutationHelper,
            mask: NDArray | str | None = None) -> nornir_imageregistration.ImagePermutationHelper:
        """Add an image to the manager"""
        raise NotImplementedError()

    @abc.abstractmethod
    def __getitem__(self, key: str) -> nornir_imageregistration.ImagePermutationHelper:
        raise NotImplementedError()

    @abc.abstractmethod
    def __delitem__(self, key: str):
        raise NotImplementedError()

    @abc.abstractmethod
    def __contains__(self, key: str) -> bool:
        raise NotImplementedError()

    @abc.abstractmethod
    def add_change_event_listener(self, func: ImageManagerChangeCallback):
        raise NotImplementedError()

    @abc.abstractmethod
    def remove_change_event_listener(self, func: ImageManagerChangeCallback):
        raise NotImplementedError()
