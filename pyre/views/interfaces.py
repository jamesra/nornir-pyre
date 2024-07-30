from abc import ABC, abstractmethod

import numpy as np
from numpy._typing import NDArray

import nornir_imageregistration

from pyre import Space
from pyre.viewmodels.transformcontroller import TransformController


class IGLPanel(ABC):
    """
    Interface to a UI Panel that supports OpenGL rendering
    """

    def swap_buffers(self):
        """Swap the front and back buffers"""
        raise NotImplementedError()


class IImageTransformView(ABC):
    """
    Base class for ImageTransformView objects
    """

    @property
    @abstractmethod
    def width(self) -> int:
        """Width of the image in pixels"""
        raise NotImplementedError()

    @property
    @abstractmethod
    def height(self) -> int:
        """Height of the image in pixels"""
        raise NotImplementedError()

    @property
    @abstractmethod
    def transform(self) -> nornir_imageregistration.ITransform:
        """transform applied to the image to move it from source to target space"""
        raise NotImplementedError()

    @property
    @abstractmethod
    def transform_controller(self) -> TransformController:
        raise NotImplementedError()

    @abstractmethod
    def draw(self,
             view_proj: NDArray[np.floating],
             space: Space,
             bounding_box: nornir_imageregistration.Rectangle | None = None):
        """Draw the image in either source (fixed) or target (warped) space"""
        raise NotImplementedError()
