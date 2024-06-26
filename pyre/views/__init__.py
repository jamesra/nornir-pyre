__all__ = ['CompositeTransformView', 'ImageTransformView', 'MosaicView']

import ctypes

import numpy
from numpy.typing import NDArray
import scipy.spatial
import OpenGL.GL as gl
from OpenGL.arrays import vbo

from .compositetransformview import CompositeTransformView
from . import compositetransformview
from .mosaicview import MosaicView
from .pointset_view import PointSetView
from .controlpoint_view import ControlPointView
from .imagetransformview import ImageTransformView


def LineIndiciesFromTri(T: scipy.spatial.Delaunay) -> list[int]:
    """
    :param ndarray T: numpy array of triangle indicies
    :rtype: list
    :returns: 1D list of triangle indicies
    """

    LineIndicies = []

    # Triangles = numpy.array(T)
    # if Triangles.ndim == 1:
    #    Triangles = Triangles.reshape(len(Triangles) // 3, 3)

    for tri in T.simplices:
        LineIndicies.append(tri[0])
        LineIndicies.append(tri[1])
        LineIndicies.append(tri[1])
        LineIndicies.append(tri[2])
        LineIndicies.append(tri[2])
        LineIndicies.append(tri[0])

    return LineIndicies


def DrawTriangles(verts, Triangles: scipy.spatial.Delaunay):
    LineIndicies = LineIndiciesFromTri(Triangles)
    if len(LineIndicies) == 0:
        return

    zCoords = numpy.ones((len(verts), 1), dtype=verts.dtype)
    Points = numpy.hstack((verts, zCoords))

    FlatPoints = Points.ravel().tolist()
    vertarray = (gl.GLfloat * len(FlatPoints))(*FlatPoints)


#    gl.glDisable(gl.GL_TEXTURE_2D)
# gl.glColor4f(1.0, 0, 0, 1.0)
# pyglet.graphics.draw_indexed(len(vertarray) // 3,
#                              gl.GL_LINES,
#                              LineIndicies,
#                              ('v3f', vertarray))
# pyglet.gl.glColor4f(1.0, 1.0, 1.0, 1.0)


def VertsForRectangle(rect):
    verts = numpy.vstack((rect.BottomLeft,
                          rect.TopLeft,
                          rect.TopRight,
                          rect.BottomRight))

    verts = numpy.fliplr(verts)

    Points = numpy.hstack((verts, numpy.ones((4, 1))))

    print("rect: %s" % (str(rect)))

    FlatPoints = Points.ravel().tolist()
    vertarray = (gl.GLfloat * len(FlatPoints))(*FlatPoints)

    return vertarray


def DrawRectangle(rect, color):
    """Draw a rectangle"""

    vertarray = VertsForRectangle(rect)

    LineIndicies = [0, 1, 1, 2, 2, 3, 3, 0]

    gl.glDisable(gl.GL_TEXTURE_2D)
    pyglet.gl.glColor4f(color[0], color[1], color[2], color[3])
    pyglet.graphics.draw_indexed(len(vertarray) / 3,
                                 gl.GL_LINES,
                                 LineIndicies,
                                 ('v3f', vertarray))

    pyglet.gl.glColor4f(1.0, 1.0, 1.0, 1.0)


def SetDrawTextureState():
    # gl.glEnable(gl.GL_TEXTURE_2D)
    gl.glDisable(gl.GL_CULL_FACE)
    gl.glEnable(gl.GL_DEPTH_TEST)

    gl.glEnable(gl.GL_BLEND)
    gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)

    # gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_S, gl.GL_CLAMP_TO_BORDER)
    # gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_T, gl.GL_CLAMP_TO_BORDER)
    # gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_NEAREST)
    # gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_NEAREST)
    # gl.glEnable(gl.GL_BLEND)
    # gl.glBlendFunc(gl.GL_ONE, gl.GL_ONE)
    gl.glDepthFunc(gl.GL_LESS)


def SetDrawMosaicState():
    gl.glEnable(gl.GL_TEXTURE_2D)
    gl.glDisable(gl.GL_CULL_FACE)
    gl.glEnable(gl.GL_DEPTH_TEST)

    gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_S, gl.GL_CLAMP_TO_BORDER)
    gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_T, gl.GL_CLAMP_TO_BORDER)
    gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_NEAREST)
    gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_NEAREST)
    gl.glEnable(gl.GL_BLEND)
    gl.glBlendFunc(gl.GL_ONE, gl.GL_ZERO)
    gl.glDepthFunc(gl.GL_LESS)


def ClearDrawTextureState():
    """Reset the GL device from drawing textures"""

    gl.glBlendEquation(gl.GL_FUNC_ADD)
    gl.glClearColor(1.0, 1.0, 1.0, 1.0)
    gl.glDisable(gl.GL_BLEND)


def DrawTexture(texture, vertarray, texarray, verts, color=None, glFunc=gl.GL_FUNC_ADD):
    if color is None:
        color = (1.0, 1.0, 1.0, 1.0)

    gl.glBlendEquation(glFunc)
    gl.glBindTexture(gl.GL_TEXTURE_2D, texture)
    gl.glColor4f(color[0], color[1], color[2], color[3])

    #     pyglet.graphics.draw_indexed(len(vertarray) / 3,
    #                                   gl.GL_TRIANGLES,
    #                                   verts.tolist(),
    #                                   ('v3f', vertarray),
    #                                   ('t2f', texarray))

    draw_indexed_custom(len(vertarray) / 3,
                        gl.GL_TRIANGLES,
                        verts.tolist(),
                        ('v3f', vertarray),
                        ('t2f', texarray))


def DrawTextureWithBuffers(texture, vertex_buffer: vbo.VBO, texture_buffer: vbo.VBO, index_buffer: vbo.VBO, color=None,
                           glFunc=gl.GL_FUNC_ADD):
    if color is None:
        color = (1.0, 1.0, 1.0, 1.0)

    try:

        gl.glEnableClientState(gl.GL_VERTEX_ARRAY)
        vertex_buffer.bind()
        gl.EnableClientState(gl.GL_INDEX_ARRAY)
        index_buffer.bind()

        gl.glVertexPointer(vertex_buffer)
        gl.glIndexPointer(index_buffer)

    finally:
        vertex_buffer.unbind()
        index_buffer.unbind()
        #
        # gl.glBlendEquation(glFunc)
        # gl.glBindTexture(gl.GL_TEXTURE_2D, texture)
        # gl.glColor4f(color[0], color[1], color[2], color[3])
        #
        # #     pyglet.graphics.draw_indexed(len(vertarray) / 3,
        # #                                   gl.GL_TRIANGLES,
        # #                                   verts.tolist(),
        # #                                   ('v3f', vertarray),
        # #                                   ('t2f', texarray))
        #
        # draw_indexed_from_buffer(len(vertarray) / 3,
        #                          gl.GL_TRIANGLES,
        #                          verts.tolist(),
        #                          buffers)


AttributeLookup = {}


def GetOrCreateAttribute(fmt):
    global AttributeLookup

    if fmt not in AttributeLookup:
        attribute = pyglet.graphics.vertexattribute.create_attribute(fmt)
        AttributeLookup[fmt] = attribute

    return AttributeLookup[fmt]


def GetOrCreateBuffer(size: int, fmt: str, array: NDArray[numpy.floating]):
    """
    Generate the attributes used in the GL draw_indexed call
    """

    result = vbo.VBO(array, fmt)
    attribute = pyglet.graphics.vertexattribute.create_attribute(fmt)
    assert size == len(array) // attribute.count, f'Data for {fmt} is incorrect length'

    buffer = pyglet.graphics.vertexbuffer.create_mappable_buffer(int(size * attribute.stride), vbo=False)
    attribute.set_region(buffer, 0, int(size), array)
    attribute.enable()
    attribute.set_pointer(buffer.ptr)

    return attribute, buffer


def GetOrCreateBuffers(size: int, *data: list[tuple[str, numpy.ndarray]]):
    """Generate the attributes used in the GL draw_indexed call
    """

    buffers = []
    for fmt, array in data:
        attribute, buffer = GetOrCreateBuffer(size, fmt, array)
        buffers.append((attribute, buffer))

    return buffers


def draw_indexed_custom(size, mode, indices, *data):
    """Draw a primitive with indexed vertices immediately.

    :Parameters:
        `size` : int
            Number of vertices given
        `mode` : int
            OpenGL drawing mode, e.g. ``GL_TRIANGLES``
        `indices` : sequence of int
            Sequence of integers giving indices into the vertex list.
        `data` : data items
            Attribute formats and data.  See the module summary for details.

    """
    glPushClientAttrib(GL_CLIENT_VERTEX_ARRAY_BIT)

    size = int(size)

    buffers = []
    for fmt, array in data:
        # #attribute = vertexattribute.create_attribute(fmt)
        attribute = GetOrCreateAttribute(fmt)
        assert size == len(array) // attribute.count, 'Data for %s is incorrect length' % fmt

        buffer = pyglet.graphics.vertexbuffer.create_mappable_buffer(size * int(attribute.stride), vbo=False)
        attribute.set_region(buffer, 0, size, array)
        attribute.enable()
        attribute.set_pointer(buffer.ptr)
        buffers.append(buffer)

    if size <= 0xff:
        index_type = GL_UNSIGNED_BYTE
        index_c_type = ctypes.c_ubyte
    elif size <= 0xffff:
        index_type = GL_UNSIGNED_SHORT
        index_c_type = ctypes.c_ushort
    else:
        index_type = GL_UNSIGNED_INT
        index_c_type = ctypes.c_uint

    index_array = (index_c_type * len(indices))(*indices)
    glDrawElements(mode, len(indices), index_type, index_array)
    glFlush()

    glPopClientAttrib()


def draw_indexed_from_buffer(size: int, vertex_buffer: vbo.VBO, index_buffer: vbo.VBO, mode: int = gl.GL_TRIANGLES):
    """Draw a primitive with indexed vertices immediately.

    :Parameters:
        `size` : int
            Number of vertices given
        `mode` : int
            OpenGL drawing mode, e.g. ``GL_TRIANGLES``
        `indices` : sequence of int
            Sequence of integers giving indices into the vertex list.
        `data` : data items
            Attribute formats and data.  See the module summary for details.

    """
    gl.glPushClientAttrib(gl.GL_CLIENT_VERTEX_ARRAY_BIT)

    for attribute, buffer in vertex_buffer:
        # attribute.enable()
        attribute.set_pointer(buffer.ptr)

    if size <= 0xff:
        index_type = gl.GL_UNSIGNED_BYTE
        index_c_type = ctypes.c_ubyte
    elif size <= 0xffff:
        index_type = gl.GL_UNSIGNED_SHORT
        index_c_type = ctypes.c_ushort
    else:
        index_type = gl.GL_UNSIGNED_INT
        index_c_type = ctypes.c_uint

    index_array = (index_c_type * len(index_buffer))(*index_buffer)
    gl.glDrawElements(mode, len(index_buffer), index_type, index_array)
    gl.glFlush()

    gl.glPopClientAttrib()
