from __future__ import annotations

import abc
from abc import abstractmethod
from enum import Enum
from typing import Callable

import numpy as np
from numpy._typing import NDArray

from pyre.interfaces.action import Action


# from pyre.viewmodels.imageviewmodel import ImageViewModel


class IImageViewModelManager(abc.ABC):
    """Shares GL ImageViewModels between views."""

    @abstractmethod
    def __getitem__(self, name: str | Enum) -> 'ImageViewModel':
        """Get the GL ImageViewModel for the image"""
        raise NotImplementedError()

    @abstractmethod
    def __contains__(self, item: str | Enum):
        raise NotImplementedError()

    @abstractmethod
    def add(self, name: str | Enum, image: NDArray[np.floating]) -> 'ImageViewModel':
        """Create GL ImageViewModel for the image and store them in the manager"""
        raise NotImplementedError()

    @abstractmethod
    def getoradd(self, name: str | Enum, image: NDArray[np.floating]) -> 'ImageViewModel':
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


ImageViewModelManagerChangeCallback = Callable[[str, Action, 'ImageViewModel'], None]
