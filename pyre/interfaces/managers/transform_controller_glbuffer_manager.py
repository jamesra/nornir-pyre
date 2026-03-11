from __future__ import annotations
import abc

from pyre.gl_engine import GLBuffer, GLIndexBuffer
from pyre.interfaces.managers import BufferType, GLBufferCollection


class ITransformControllerGLBufferManager(abc.ABC):
    """Interface to a class that returns GL Buffers for transform control points"""

    @abc.abstractmethod
    def __getitem__(self, item: 'pyre.controllers.TransformController') -> GLBufferCollection:
        raise NotImplementedError()

    def __contains__(self, item: 'TransformController') -> bool:
        raise NotImplementedError()

    @abc.abstractmethod
    def get_glbuffer(self, key: 'TransformController', type: BufferType) -> GLBuffer | GLIndexBuffer:
        """Fetch the gl buffer for a transform controller of the requested type"""
        raise NotImplementedError()

    @abc.abstractmethod
    def add(self, transform_controller: 'TransformController') -> GLBufferCollection:
        """Removes buffers for a transform controller"""
        raise NotImplementedError()

    @abc.abstractmethod
    def remove(self, transform_controller: 'TransformController'):
        """Adds buffers for a transform controller"""
        raise NotImplementedError()

    @abc.abstractmethod
    def add_on_transform_controller_add_remove_event_listener(self, func):
        """Notify when a transform controller is added or removed."""
        raise NotImplementedError()

    @abc.abstractmethod
    def remove_on_transform_controller_add_remove_event_listener(self, func):
        """Stop notifying when a transform controller is added or removed."""
        raise NotImplementedError()
