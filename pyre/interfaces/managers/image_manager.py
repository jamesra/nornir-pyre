from __future__ import annotations

import abc
from enum import Enum
from typing import Callable

from numpy.typing import NDArray

import nornir_imageregistration
from pyre.interfaces.action import Action
from pyre.interfaces.named_tuples import ImageLoadResult, LoadStosResult


class IImageLoader(abc.ABC):

    @abc.abstractmethod
    def load_stos(self, stos_path: str) -> LoadStosResult:
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
