import ctypes
from typing import Sequence

from OpenGL import GL as gl

from pyre.gl_engine.helpers import get_gl_type_size, check_for_error
from pyre.gl_engine.vertex_attribute import VertexAttribute


class VertexArrayLayout:
    """Represents all vertex attributes for a shader program.  Attributes must appear
    in the the list in the same order they appear in the vertex array columns"""
    _attributes: Sequence[VertexAttribute]

    @property
    def attributes(self) -> Sequence[VertexAttribute]:
        return self._attributes

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
            # gl.glVertexAttribPointer(attrib.location, attrib.num_elements, attrib.type, False, shader.attribute_stride,
            #                          None if attrib.offset == 0 else attrib.offset)
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
