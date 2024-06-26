import abc
from typing import Callable
from pyre.space import Space
from pyre.state.action import Action
from pyre.viewmodels.transformcontroller import TransformController

TransformControllerAddRemoveCallback = Callable[[Action, TransformController], None]
TransformControllerChangedCallback = Callable[[TransformController], None]
ImageChangedCallback = Callable[[Space], None]


class IStateEvents(abc.ABC):

    @abc.abstractmethod
    def AddTransformControllerChangeEventListener(self, func: TransformControllerChangedCallback):
        raise NotImplementedError()

    @abc.abstractmethod
    def RemoveTransformControllerChangeEventListener(self, func: TransformControllerChangedCallback):
        raise NotImplementedError()

    @abc.abstractmethod
    def AddImageViewModelChangeEventListener(self, func: ImageChangedCallback):
        raise NotImplementedError()

    @abc.abstractmethod
    def RemoveImageViewModelChangeEventListener(self, func: ImageChangedCallback):
        raise NotImplementedError()


class StateEventsImpl(IStateEvents):
    """
    Straightforward implementation of IStateEvents
    """
    _OnTransformControllerChangeEventListeners: list[TransformControllerChangedCallback]
    _OnImageChangeEventListeners: list[ImageChangedCallback]

    def __init__(self):
        self._OnTransformControllerChangeEventListeners = []
        self._OnImageChangeEventListeners = []

    def AddTransformControllerChangeEventListener(self, func: TransformControllerChangedCallback):
        self._OnTransformControllerChangeEventListeners.append(func)

    def RemoveTransformControllerChangeEventListener(self, func: TransformControllerChangedCallback):
        self._OnTransformControllerChangeEventListeners.remove(func)

    def _FireOnTransformControllerChanged(self, transform_controller: TransformController):
        for func in self._OnTransformControllerChangeEventListeners:
            func(transform_controller)

    def AddImageViewModelChangeEventListener(self, func: ImageChangedCallback):
        self._OnImageChangeEventListeners.append(func)

    def RemoveImageViewModelChangeEventListener(self, func: ImageChangedCallback):
        self._OnImageChangeEventListeners.remove(func)

    def _FireOnImageChanged(self, space: Space):
        for func in self._OnImageChangeEventListeners:
            func(space)
