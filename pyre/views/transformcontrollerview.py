import numpy as np
from numpy.typing import NDArray
import pyre
from pyre.space import Space
from pyre.views.controlpoint_view import ControlPointView


class TransformControllerView:
    """Renders the control points of a transform"""
    _transform_controller: pyre.viewmodels.TransformController
    _control_point_view: ControlPointView

    def __init__(self,
                 transform_controller: pyre.viewmodels.TransformController | None,
                 texture_array: int):
        """
        :param transform_controller:
        :param texture_array: The texture array that contains a texture for unselected points at index 0 and
        selected points at index 1
        """
        self._transform_controller = transform_controller
        self._OnTransformControllerChange(transform_controller)
        pyre.state.currentStosConfig.AddOnTransformControllerChangeEventListener(self._OnTransformControllerChange)
        self._control_point_view = ControlPointView(self._transform_controller.points, texture_array)

    def _OnTransformControllerChange(self, new_transform_controller: pyre.viewmodels.TransformController | None):
        if self._transform_controller is not None:
            self._transform_controller.RemoveOnChangeEventListener(self._OnTransformChange)

        self._transform_controller = new_transform_controller

        if self._transform_controller is not None:
            self._transform_controller.AddOnChangeEventListener(self._OnTransformChange)

    def _OnTransformChange(self):
        self._control_point_view.points = self._transform_controller.points

    @property
    def selected(self) -> NDArray[bool]:
        return self._control_point_view.texture_index.astype(bool)

    @selected.setter
    def selected(self, value: NDArray[bool]):
        self._control_point_view.texture_index = value.astype(np.uint16)

    def draw(self, model_view_proj_matrix: NDArray[np.floating], space: Space, scale_factor: float):
        tween = 0 if space == Space.Source else 1
        self._control_point_view.draw(model_view_proj_matrix, tween, scale_factor)
