"""Maps images to GL textures. Read-only."""
from __future__ import annotations

from enum import Enum
from threading import Lock

import numpy as np
from numpy.typing import NDArray

from pyre.eventmanager import wxEventManager
from pyre.interfaces.eventmanager import IEventManager
from pyre.interfaces.managers import IImageViewModelManager, ImageViewModelManagerChangeCallback
from pyre.interfaces.action import Action
from pyre.interfaces.viewtype import convert_to_key
from pyre.viewmodels.imageviewmodel import ImageViewModel


class ImageViewModelManager(IImageViewModelManager):
    _models = dict[str, ImageViewModel]
    # _glcontext_manager: IGLContextManager
    _change_event_manager: IEventManager[ImageViewModelManagerChangeCallback]
    _lock: Lock

    def __init__(self):
        self._models = {}
        self._change_event_listeners = []
        self._lock = Lock()
        self._change_event_manager = wxEventManager[ImageViewModelManagerChangeCallback]()
        # self._glcontext_manager = glcontext_manager
        # self._glcontext_manager.add_glcontext_added_event_listener(self._on_glcontext_added)

    def __getitem__(self, name: str | Enum) -> ImageViewModel:
        """Get the GL ImageViewModel for the image"""
        key = convert_to_key(name)
        return self._models[key]

    def __contains__(self, item: str | Enum):
        key = convert_to_key(item)
        return key in self._models

    def __delitem__(self, key: str | Enum):
        print(f"Removing image viewmodel {key}")
        key = convert_to_key(key)
        if key not in self._models:
            raise KeyError(f"Image {key} does not exist in the manager")

        value = self._models[key]
        del self._models[key]
        self._fire_change_event(key, Action.REMOVE, value)

    def add(self, name: str | Enum, image: NDArray[np.floating] | None) -> ImageViewModel:
        """Create GL ImageViewModel for the image and store them in the manager"""
        key = convert_to_key(name)
        del name

        with self._lock:
            if key in self._models:
                raise KeyError(f"Image {key} already exists in the manager")

            print(f"Adding image viewmodel {key}")

            # Create a new ImageViewModel using the NDArray if it is passed, otherwise assume name is a filename
            parameter = key if image is None else image
            new_model = ImageViewModel(parameter)
            self._models[key] = new_model
            self._fire_change_event(key, Action.ADD, new_model)
            return new_model

    def setdefault(self, name: str | Enum, image: NDArray[np.floating] | None) -> ImageViewModel:
        """Get the GL ImageViewModel for the image, creating one if it does not exist."""
        return self.getoradd(name, image)

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

        with self._lock:
            model = self._models[key]
            del self._models[key]
            self._fire_change_event(key, Action.REMOVE, model)

    def _fire_change_event(self, name: str, action: Action, model: ImageViewModel):
        """Notify listeners of a change"""
        self._change_event_manager.invoke(name, action, model)

    def add_change_event_listener(self, func: ImageViewModelManagerChangeCallback):
        """Callbacks are invoked when a GLContext is created, or if a context already exists,
         immediately upon registration."""
        self._change_event_manager.add(func)

    def remove_change_event_listener(self, func: ImageViewModelManagerChangeCallback):
        """Callbacks are invoked when a GLContext is created, or if a context already exists,
         immediately upon registration."""
        self._change_event_manager.remove(func)
