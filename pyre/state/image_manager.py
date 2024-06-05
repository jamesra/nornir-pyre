"""Handles shared image resources"""
import abc
import numpy as np
from typing import Callable
from numpy.typing import NDArray
import nornir_imageregistration
from enum import Enum
from .viewtype import convert_to_key
from .events import Action

# Change event for the ImageManager, passes the key and the ImagePermutationHelper associated with the key
ImageManagerChangeCallback = Callable[[Action, str, nornir_imageregistration.ImagePermutationHelper], None]


class IImageManager(abc.ABC):

    @abc.abstractmethod
    def add(self,
            key: str,
            image: str | NDArray | nornir_imageregistration.ImagePermutationHelper,
            mask: NDArray | str | None = None)  -> nornir_imageregistration.ImagePermutationHelper
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


class ImageManager(IImageManager):
    _images: dict[str, nornir_imageregistration.ImagePermutationHelper]
    _change_event_listeners: list[ImageManagerChangeCallback]

    def __init__(self):
        self._images = {}

    def add(self,
            key: str | Enum,
            image: str | NDArray | nornir_imageregistration.ImagePermutationHelper,
            mask: NDArray | str | None = None) -> nornir_imageregistration.ImagePermutationHelper:
        key = convert_to_key(key)
        if key in self._images:
            raise KeyError(f"Image with key {key} already exists in the manager")

        if isinstance(image, nornir_imageregistration.ImagePermutationHelper):
            if mask is not None:
                raise ValueError("Cannot provide a mask when image parameter is an ImagePermutationHelper")
            permutations = image
        else:
            permutations = nornir_imageregistration.ImagePermutationHelper(image, mask)

        self._images[key] = permutations
        return permutations

    def __delitem__(self, key: str | Enum):
        key = convert_to_key(key)
        del self._images[key]

    def __contains__(self, key: str | Enum) -> bool:
        key = convert_to_key(key)
        return key in self._images

    def __getitem__(self, key: str | Enum) -> nornir_imageregistration.ImagePermutationHelper:
        key = convert_to_key(key)
        return self._images[key]

    def add_change_event_listener(self, func: ImageManagerChangeCallback):
        """Callbacks are invoked when a GLContext is created, or if a context already exists,
         immediately upon registration."""
        self._change_event_listeners.append(func)

    def remove_change_event_listener(self, func: ImageManagerChangeCallback):
        """Callbacks are invoked when a GLContext is created, or if a context already exists,
         immediately upon registration."""
        self._change_event_listeners.remove(func)
