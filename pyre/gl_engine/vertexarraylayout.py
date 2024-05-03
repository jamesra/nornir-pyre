import ctypes
from typing import Sequence

from OpenGL import GL as gl

from pyre.gl_engine import check_for_error, get_gl_type_size
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
