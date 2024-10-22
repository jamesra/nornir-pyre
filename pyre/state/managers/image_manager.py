"""Handles shared image resources"""
from enum import Enum
import nornir_imageregistration

from numpy.typing import NDArray
from pyre.interfaces.eventmanager import IEventManager
from pyre.eventmanager import wxEventManager
from pyre.interfaces.managers.image_manager import IImageManager, ImageManagerChangeCallback

from pyre.interfaces.action import Action
from pyre.interfaces.viewtype import convert_to_key


class ImageManager(IImageManager):
    _images: dict[str, nornir_imageregistration.ImagePermutationHelper]
    _change_event_manager: IEventManager[ImageManagerChangeCallback]

    def __init__(self):
        self._images = {}
        self._change_event_manager = wxEventManager[ImageManagerChangeCallback](self.__class__.__name__)

    def add(self,
            key: str | Enum,
            image: str | NDArray | nornir_imageregistration.ImagePermutationHelper,
            mask: NDArray | str | None = None) -> nornir_imageregistration.ImagePermutationHelper:
        key = convert_to_key(key)
        if key in self._images:
            raise KeyError(f"Image with key {key} already exists in the manager")

        print(f"Adding image {key}")
        if isinstance(image, nornir_imageregistration.ImagePermutationHelper):
            if mask is not None:
                raise ValueError("Cannot provide a mask when image parameter is an ImagePermutationHelper")
            permutations = image
        else:
            permutations = nornir_imageregistration.ImagePermutationHelper(image, mask)

        self._images[key] = permutations
        self._change_event_manager.invoke(Action.ADD, key, permutations)
        return permutations

    def __delitem__(self, key: str | Enum):
        print(f"Removing image {key}")
        key = convert_to_key(key)
        value = self._images[key]
        del self._images[key]
        self._change_event_manager.invoke(Action.REMOVE, key, value)

    def __contains__(self, key: str | Enum) -> bool:
        key = convert_to_key(key)
        return key in self._images

    def __getitem__(self, key: str | Enum) -> nornir_imageregistration.ImagePermutationHelper:
        key = convert_to_key(key)
        return self._images[key]

    def add_change_event_listener(self, func: ImageManagerChangeCallback):
        """Callbacks are invoked when a GLContext is created, or if a context already exists,
         immediately upon registration."""
        self._change_event_manager.add(func)

    def remove_change_event_listener(self, func: ImageManagerChangeCallback):
        """Callbacks are invoked when a GLContext is created, or if a context already exists,
         immediately upon registration."""
        self._change_event_manager.remove(func)
