from __future__ import annotations
import numpy as np
from numpy.typing import NDArray

import nornir_imageregistration
from pyre.gl_engine import GLBuffer
from pyre.gl_engine.shaders import controlpointset_shader
from pyre.controllers.transformcontroller import TransformController


class TransformGLViewModel:
    """Provides GL Buffers for transform control points and exposes a selection state for each point.
    We create one of these for the current transform, and share buffers across all GL Contexts"""
    _transform_model: nornir_imageregistration.ITransform
    _point_buffer: GLBuffer
    _texture_index_buffer: GLBuffer

    @property
    def TransformModel(self) -> nornir_imageregistration.ITransform:
        """The transform this controller is editting"""
        return self._transform_model

    @TransformModel.setter
    def TransformModel(self, value: nornir_imageregistration.ITransform):
        if self._transform_model is not None:
            self._transform_model.RemoveOnChangeEventListener(self.OnTransformChanged)

        self._transform_model = value

        if value is not None:
            assert (isinstance(value, nornir_imageregistration.ITransformChangeEvents))
            self._transform_model.AddOnChangeEventListener(self.OnTransformChanged)

        self._OnTransformChange()

    def __init__(self, transform_controller: TransformController, texture_array: int):
        """
        :param transform_controller:
        :param texture_array: The texture array that contains a texture for unselected points at index 0 and
        selected points at index 1
        """
        self._transform_controller = transform_controller
        self._OnTransformControllerChange(transform_controller)
        transform_controller.AddOnChangeEventListener(self._OnTransformChange)

    def create_open_gl_objects(self, points, texture_indicies=None):
        self._point_buffer = GLBuffer(layout=controlpointset_shader.pointset_layout, data=points,
                                      usage=gl.GL_DYNAMIC_DRAW)
        self._texture_index_buffer = GLBuffer(layout=controlpointset_shader.texture_index_layout,
                                              data=texture_indicies, usage=gl.GL_DYNAMIC_DRAW)

    def _OnTransformControllerChange(self, new_transform_controller: TransformController):
        if self._transform_controller is not None:
            self._transform_controller.RemoveOnChangeEventListener(self._OnTransformChange)

        self._transform_controller = new_transform_controller

        if self._transform_controller is not None:
            self._transform_controller.AddOnChangeEventListener(self._OnTransformChange)

    def _OnTransformChange(self):
        if self._transform_model is None:
            self._point_buffer.points = np.zeros((0, 4), dtype=np.float32)
            return

        self._point_buffer.points = self._transform_controller.points

    @property
    def selected(self):
        return self._texture_index_buffer.data.astype(bool)

    @selected.setter
    def selected(self, value: NDArray[bool]):
        if value is None:
            value = np.zeros(self._point_buffer.data.shape[0], dtype=np.uint16)

        if len(value) != self._point_buffer.data.shape[0]:
            raise ValueError("Selection array must have the same number of elements as the point buffer")

        self._texture_index_buffer.data = value
