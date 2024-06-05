"""Maps images to GL textures. Read-only."""
from __future__ import annotations

import abc
from abc import abstractmethod
from typing import Callable
from enum import Enum
import numpy as np
from numpy.typing import NDArray
from .events import Action

from .viewtype import convert_to_key

import pyre.viewmodels
from pyre.viewmodels.imageviewmodel import ImageViewModel
from pyre.state.gl_context_manager import IGLContextManager

ImageViewModelManagerChangeCallback = Callable[['IImageViewModelManager', str, Action, ImageViewModel], None]


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


class ImageViewModelManager(IImageViewModelManager):
    _models = dict[str, ImageViewModel]
    # _glcontext_manager: IGLContextManager
    _change_event_listeners: list[ImageViewModelManagerChangeCallback]

    def __init__(self):
        self._models = {}
        self._change_event_listeners = []
        # self._glcontext_manager = glcontext_manager
        # self._glcontext_manager.add_glcontext_added_event_listener(self._on_glcontext_added)

    def __getitem__(self, name: str | Enum) -> ImageViewModel:
        """Get the GL ImageViewModel for the image"""
        key = convert_to_key(name)
        return self._models[key]

    def __contains__(self, item: str | Enum):
        key = convert_to_key(item)
        return key in self._models

    def add(self, name: str | Enum, image: NDArray[np.floating] | None) -> ImageViewModel:
        """Create GL ImageViewModel for the image and store them in the manager"""
        key = convert_to_key(name)
        del name
        if key in self._models:
            raise KeyError(f"Image {key} already exists in the manager")

        # Create a new ImageViewModel using the NDArray if it is passed, otherwise assume name is a filename
        parameter = key if image is None else image
        new_model = ImageViewModel(parameter)
        self._models[key] = new_model
        self._fire_change_event(key, Action.ADD, new_model)
        return new_model

    def getoradd(self, name: str | Enum, image: NDArray[np.floating] | None) -> ImageViewModel:
        """Get the GL ImageViewModel for the image, creating one if it does not exist"""
        key = convert_to_key(name)
        del name
        if key in self._models:
            return self._models[key]

        return self.add(key, image)

    def remove(self, name: str | Enum) -> None:
        key = convert_to_key(name)
        del name
        model = self._models[key]
        del self._models[key]
        self._fire_change_event(key, Action.REMOVE, model)

    def _fire_change_event(self, name: str, action: Action, model: ImageViewModel):
        """Notify listeners of a change"""
        for listener in self._change_event_listeners:
            listener(self, name, action, model)

    def add_change_event_listener(self, func: ImageViewModelManagerChangeCallback):
        """Callbacks are invoked when a GLContext is created, or if a context already exists,
         immediately upon registration."""
        self._change_event_listeners.append(func)

    def remove_change_event_listener(self, func: ImageViewModelManagerChangeCallback):
        """Callbacks are invoked when a GLContext is created, or if a context already exists,
         immediately upon registration."""
        self._change_event_listeners.remove(func)
