from __future__ import annotations

import abc
from abc import abstractmethod
from enum import Enum
from typing import Callable

from .events import Action

import numpy as np
from numpy._typing import NDArray

import nornir_imageregistration

from pyre.viewmodels import ImageViewModel


class IImageLoader(abc.ABC):

    @abc.abstractmethod
    def load_stos(self, stos_path: str) -> nornir_imageregistration.ITransform:
        raise NotImplementedError()

    @abc.abstractmethod
    def load_image_into_manager(self, key: str | Enum | None,
                                image_path: str,
                                mask_path: str | None,
                                search_dirs: list[str]) -> tuple[str, nornir_imageregistration.ImagePermutationHelper]:
        raise NotImplementedError()

    @abc.abstractmethod
    def create_image_viewmodel(self, name: str | Enum,
                               permutations: nornir_imageregistration.ImagePermutationHelper) -> ImageViewModel:
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
    def __getitem__(self, key: str) -> NDArray[np.floating]:
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


ImageViewModelManagerChangeCallback = Callable[[str, Action, ImageViewModel], None]


class IImageViewModelManager(abc.ABC):
    """Shares GL ImageViewModels between views."""

    @abstractmethod
    def __getitem__(self, name: str | Enum) -> ImageViewModel:
        """Get the GL ImageViewModel for the image"""
        raise NotImplementedError()

    @abstractmethod
    def __contains__(self, item: str | Enum):
        raise NotImplementedError()

    @abstractmethod
    def add(self, name: str | Enum, image: NDArray[np.floating]) -> ImageViewModel:
        """Create GL ImageViewModel for the image and store them in the manager"""
        raise NotImplementedError()

    @abstractmethod
    def getoradd(self, name: str | Enum, image: NDArray[np.floating]) -> ImageViewModel:
        """Get the GL ImageViewModel for the image, creating one if it does not exist"""
        raise NotImplementedError()

    @abstractmethod
    def remove(self, name: str | Enum) -> None:
        """Remove the GL ImageViewModel for the image"""
        raise NotImplementedError()

    @abstractmethod
    def add_change_event_listener(self, func: ImageViewModelManagerChangeCallback):
        """Callbacks are invoked when a GLContext is created, or if a context already exists,
         immediately upon registration."""
        raise NotImplementedError()

    @abstractmethod
    def remove_change_event_listener(self, func: ImageViewModelManagerChangeCallback):
        """Callbacks are invoked when a GLContext is created, or if a context already exists,
         immediately upon registration."""
        raise NotImplementedError()
