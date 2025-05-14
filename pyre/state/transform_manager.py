import abc

from nornir_imageregistration import ITransform
import pyre.viewmodels
from pyre.controllers.transformcontroller import TransformController
from .events import TransformControllerAddRemoveCallback


class ITransformControllerManager(abc.ABC):
    """Tracks active controllers for transforms"""

    def getoradd(self, transform: ITransform) -> TransformController:
        """Get the controller for a transform, or add a new controller if one does not exist"""
        raise NotImplementedError()

    def tryremove(self, transform_controller: TransformController) -> bool:
        """Remove the controller for a transform"""
        raise NotImplementedError()

    def __getitem__(self, key: ITransform) -> TransformController:
        """Return the transform_controller for a transform"""
        raise NotImplementedError()

    def __contains__(self, key: ITransform) -> bool:
        """Return True if the transform has a controller"""
        raise NotImplementedError()

    def AddTransformControllerAddRemoveEventListener(self, func: TransformControllerAddRemoveCallback):
        """Add a callback for when a transform controller is added or removed"""
        raise NotImplementedError()

    def RemoveTransformControllerAddRemoveEventListener(self, func: TransformControllerAddRemoveCallback):
        """Remove a callback for when a transform controller is added or removed"""
        raise NotImplementedError()


class TransformControllerManager(ITransformControllerManager):
    """Tracks the current transform that is being editted"""
    _transform_controller: pyre.controllers.TransformController
    _OnTransformControllerChangeEventListeners: list[TransformControllerAddRemoveCallback]

    def __init__(self):
        self._OnTransformControllerChangeEventListeners = []

    def AddOnTransformControllerChangeEventListener(self, func):
        self._OnTransformControllerChangeEventListeners.append(func)

    def RemoveTransformControllerChangeEventListener(self, func: TransformControllerAddRemoveCallback):
        self._OnTransformControllerChangeEventListeners.remove(func)

    def _FireOnTransformControllerChanged(self):
        for func in self._OnTransformControllerChangeEventListeners:
            func(self._transform_controller)

    @property
    def transform(self) -> pyre.controllers.TransformController | None:
        """The current transform that is being editted"""
        return self._transform_controller

    @transform.setter
    def transform(self, value: pyre.controllers.TransformController):
        self._transform_controller = value
        self._FireOnTransformControllerChanged()
