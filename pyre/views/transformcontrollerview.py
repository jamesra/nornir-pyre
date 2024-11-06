import wx.glcanvas
import numpy as np
from numpy.typing import NDArray
from typing import AbstractSet, Sequence, Iterable, Callable
from dependency_injector.wiring import Provide

from nornir_imageregistration import ITransform
import pyre
from pyre.observable import ObservableSet, ObservedAction
from pyre.container import IContainer
from pyre.controllers import TransformController
from pyre.space import Space
from pyre.views.pointview import PointView
import pyre.controllers
from pyre.interfaces.managers.buffertype import BufferType


class BinarySelectionMapper:
    """Maps an observable set of integers to a binary ndarray"""
    _selection: ObservableSet[int]
    _setter: Callable[[NDArray[bool]], None]

    def __init__(self, selection: ObservableSet[int],
                 getter: Callable[[], NDArray[bool]],
                 setter: Callable[[NDArray[bool]], None]):
        self._selection = selection
        self._getter = getter
        self._setter = setter
        self._selection.add_observer(self._OnSelectionChanged)

    def _OnSelectionChanged(self, obj: ObservableSet[int], action: ObservedAction, indicies: AbstractSet[int]):
        """Converts the set of integers to a binary array with the integer values set to true"""

        # Determine the length of the array we are writing to.
        length = len(self._getter())
        selected = np.zeros(length, dtype=bool)
        index = TransformController._ensure_numpy_friendly_index(obj)

        if np.any(index >= length):
            raise ValueError("index is out of bounds")

        # Set the values at the indicies to true
        selected[index] = True
        self._setter(selected)


class TransformControllerView:
    """Renders the control points of a transform"""
    _transform_controller: pyre.controllers.TransformController
    _controlpoint_view: PointView
    _transformglbuffer_manager: pyre.interfaces.managers.ITransformControllerGLBufferManager = Provide[
        IContainer.transform_glbuffermanager]
    _gl_context_manager: pyre.interfaces.managers.IGLContextManager = Provide[IContainer.glcontext_manager]

    _initialized: bool = False

    def __init__(self,
                 transform_controller: pyre.controllers.TransformController | None):
        """
        :param transform_controller:
        :param selected_points: A set indicating which points are selected.  If None, no points are selectable.
        selected points at index 1
        """
        self._controlpoint_view = None
        self._transform_controller = transform_controller
        self._transform_controller.AddOnChangeEventListener(self._OnTransformChange)
        self._transform_controller.AddOnModelReplacedEventListener(self._OnTransformModelReplaced)
        self._initialized = False
        self._gl_context_manager.add_glcontext_added_event_listener(self.create_objects)
        # pyre.state.currentStosConfig.AddOnTransformControllerChangeEventListener(self._OnTransformControllerChange)

    def create_objects(self, context: wx.glcanvas.GLContext):
        """"Creates opengl objects when opengl is initialized"""
        if self._initialized:
            return True

        self._initialized = True
        self._gl_context_manager.remove_glcontext_added_event_listener(self.create_objects)

        glcontrolpointbuffer = self._transformglbuffer_manager.get_glbuffer(
            self._transform_controller,
            BufferType.ControlPoint)
        glselectionbuffer = self._transformglbuffer_manager.get_glbuffer(
            self._transform_controller,
            BufferType.Selection)

        self._controlpoint_view = PointView(points=glcontrolpointbuffer,
                                            texture_indicies=glselectionbuffer,
                                            texture_array=pyre.resources.pointtextures.PointArray)

    def _OnTransformControllerChange(self, new_transform_controller: pyre.controllers.TransformController | None):
        if self._transform_controller is not None:
            self._transform_controller.RemoveOnChangeEventListener(self._OnTransformChange)

        self._transform_controller = new_transform_controller

        if self._transform_controller is not None:
            self._transform_controller.AddOnChangeEventListener(self._OnTransformChange)

    def _OnTransformChange(self, *args, **kwargs):
        if self._controlpoint_view is None:
            return

        if np.allclose(self._controlpoint_view.points, self._transform_controller.points):
            return

        reset_selection = len(self._controlpoint_view.texture_index) != self._controlpoint_view.points.shape[0]

        self._controlpoint_view.points = self._transform_controller.points

        if reset_selection:
            self.selected = None

    def _OnTransformModelReplaced(self, controller: TransformController, old: ITransform, new: ITransform):
        """The transform model object has changed.  Reset everything"""
        if self._controlpoint_view is None:
            return

        self._controlpoint_view.points = self._transform_controller.points
        self.selected = None

    @property
    def selected(self) -> NDArray[bool]:
        return self._controlpoint_view.texture_index.astype(bool)

    @selected.setter
    def selected(self, value: NDArray[bool] | NDArray[np.integer] | None):
        """
        Set the selected control points
        :param value: Passing None will deselect all points, otherwise a boolean or integer array representing the texture index that should be used for points
        :return:
        """
        if value is None:
            self._controlpoint_view.texture_index = np.zeros(self._controlpoint_view.points.shape[0], dtype=np.uint16)
            return

        if value.shape[0] != self._controlpoint_view.points.shape[0]:
            raise ValueError("Selected array must have the same number of elements as the control points")

        if value.dtype == np.integer:
            if max(value) >= self._controlpoint_view.num_textures:
                raise ValueError(
                    "Selected array of integer values contains indicies larger than the number of textures in texture array")
            if min(value) < 0:
                raise ValueError("Selected array of integer values contains indicies that are negative")

        self._controlpoint_view.texture_index = value.astype(np.uint16)

    def set_selected_by_index(self, index: Iterable[int] | NDArray[int]):
        """Converts passed sequences of integers into a boolean array where values at the index are true"""
        selected = np.zeros(self._controlpoint_view.points.shape[0], dtype=bool)
        index = TransformController._ensure_numpy_friendly_index(index)

        if np.any(index >= self._controlpoint_view.points.shape[0]):
            raise ValueError("Selected index is out of bounds")

        selected[index] = True
        self.selected = selected

    def draw(self, model_view_proj_matrix: NDArray[np.floating], tween: float, scale_factor: float):
        if self._controlpoint_view is None:
            return

        self._controlpoint_view.draw(model_view_proj_matrix, tween, scale_factor)
