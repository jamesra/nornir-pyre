import ctypes
from typing import Sequence

from OpenGL import GL as gl
import numpy as np

from pyre.gl_engine.helpers import check_for_error, get_dtype_for_gl_type, get_gl_type_size
from pyre.gl_engine.vertex_attribute import VertexAttribute


class VertexArrayLayout:
    """Represents all vertex attributes for a shader program.  Attributes must appear
    in the the list in the same order they appear in the vertex array columns"""
    _attributes: Sequence[VertexAttribute]

    @property
    def attributes(self) -> Sequence[VertexAttribute]:
        return self._attributes

    @property
    def total_elements(self) -> int:
        """Total number of elements in the vertex array"""
        return sum(attr.num_elements for attr in self.attributes)

    @property
    def common_attribute_type(self):
        """Check if all attribute types are the same and return the common type if they are."""
        types = {attr.type for attr in self.attributes}
        if len(types) == 1:
            return next(iter(types))
        else:
            return None

    @property
    def dtype(self) -> np.dtype:
        """The numpy data type of the vertex array, if all attributes have the same type"""
        common_type = self.common_attribute_type
        if common_type is None:
            raise ValueError("Attributes have different types")

        return get_dtype_for_gl_type(common_type)

    @property
    def stride(self) -> int:
        """Stride of the attributes"""
        return sum(attr.num_elements * get_gl_type_size(attr.type) for attr in self.attributes)

    def __init__(self, attributes: Sequence[VertexAttribute]):
        self._attributes = attributes

    def add_vertex_attributes(self):
        """Bind offsets in a buffer to specified vertex attributes
        The vao must be bound before calling this function
        """

        stride = self.stride
        offset = 0
        for attrib in self.attributes:
            location = attrib.location()
            gl.glVertexAttribPointer(index=location,
                                     size=attrib.num_elements,
                                     type=attrib.type,
                                     normalized=False,
                                     stride=stride,
                                     pointer=ctypes.c_void_p(offset))
            check_for_error()

            gl.glVertexAttribDivisor(location, 1 if attrib.instanced else 0)
            check_for_error()

            offset += attrib.num_elements * get_gl_type_size(attrib.type)

            gl.glEnableVertexAttribArray(location)
            check_for_error()
