from __future__ import annotations

import abc
from abc import ABC
from typing import Callable, Generic, TypeVar

EventCallbackType = TypeVar('EventCallbackType', bound=Callable)


class IEventManager(ABC, Generic[EventCallbackType]):
    """Interface for an event manager"""

    @abc.abstractmethod
    def add(self, func: EventCallbackType):
        """Add a listener to the event manager"""
        raise NotImplementedError()

    @abc.abstractmethod
    def remove(self, func: EventCallbackType):
        """Remove a listener from the event manager"""
        raise NotImplementedError()

    @abc.abstractmethod
    def invoke(self, *args, **kwargs):
        """Invoke an event"""
        raise NotImplementedError()
