"""
Legacy OpenGL draw helpers. Some functions depend on pyglet for vertex attributes/buffers.
Used by pyre.views; re-exported there for backward compatibility.
"""
import ctypes

import OpenGL.GL as gl
from OpenGL.arrays import vbo
from PyQt6.QtOpenGL import QOpenGLFunctions_4_1_Core as QOpenGLFunctions
import numpy
from numpy.typing import NDArray
import scipy.spatial

from pyre.gl_engine.helpers import raise_on_error

# Legacy code path: pyglet used for draw_indexed_custom, GetOrCreateAttribute, DrawRectangle
try:
    import pyglet  # type: ignore[import-untyped]
except ImportError:
    pyglet = None  # type: ignore


def LineIndicesFromTri(T: scipy.spatial.Delaunay) -> list[int]:
    """
    :param ndarray T: numpy array of triangle indices
    :rtype: list
    :returns: 1D list of triangle indices
    """
    line_indices = []
    for tri in T.simplices:
        line_indices.append(tri[0])
        line_indices.append(tri[1])
        line_indices.append(tri[1])
        line_indices.append(tri[2])
        line_indices.append(tri[2])
        line_indices.append(tri[0])
    return line_indices


def DrawTriangles(verts, Triangles: scipy.spatial.Delaunay):
    line_indices = LineIndicesFromTri(Triangles)
    if len(line_indices) == 0:
        return

    zCoords = numpy.ones((len(verts), 1), dtype=verts.dtype)
    Points = numpy.hstack((verts, zCoords))
    FlatPoints = Points.ravel().tolist()
    vertarray = (gl.GLfloat * len(FlatPoints))(*FlatPoints)
    # Legacy: actual draw would use pyglet or gl; currently no draw call here (commented out in original)


def VertsForRectangle(rect):
    verts = numpy.vstack((rect.BottomLeft,
                          rect.TopLeft,
                          rect.TopRight,
                          rect.BottomRight))
    verts = numpy.fliplr(verts)
    Points = numpy.hstack((verts, numpy.ones((4, 1))))
    FlatPoints = Points.ravel().tolist()
    vertarray = (gl.GLfloat * len(FlatPoints))(*FlatPoints)
    return vertarray


def DrawRectangle(rect, color):
    """Draw a rectangle. Legacy: uses pyglet."""
    if pyglet is None:
        raise RuntimeError("DrawRectangle requires pyglet")
    vertarray = VertsForRectangle(rect)
    line_indices = [0, 1, 1, 2, 2, 3, 3, 0]
    pyglet.gl.glColor4f(color[0], color[1], color[2], color[3])
    pyglet.graphics.draw_indexed(len(vertarray) / 3,
                                 gl.GL_LINES,
                                 line_indices,
                                 ('v3f', vertarray))
    pyglet.gl.glColor4f(1.0, 1.0, 1.0, 1.0)


def SetDrawTextureState(funcs: QOpenGLFunctions):
    funcs.glDisable(gl.GL_CULL_FACE)
    funcs.glEnable(gl.GL_DEPTH_TEST)
    funcs.glEnable(gl.GL_BLEND)
    funcs.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
    funcs.glDepthFunc(gl.GL_LESS)


def SetDrawMosaicState():
    gl.glDisable(gl.GL_CULL_FACE)
    raise_on_error("after glDisable(GL_CULL_FACE) in SetDrawMosaicState")
    gl.glEnable(gl.GL_DEPTH_TEST)
    raise_on_error("after glEnable(GL_DEPTH_TEST) in SetDrawMosaicState")
    gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_S, gl.GL_CLAMP_TO_BORDER)
    raise_on_error("after glTexParameteri(WRAP_S) in SetDrawMosaicState")
    gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_T, gl.GL_CLAMP_TO_BORDER)
    raise_on_error("after glTexParameteri(WRAP_T) in SetDrawMosaicState")
    gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_NEAREST)
    raise_on_error("after glTexParameteri(MAG_FILTER) in SetDrawMosaicState")
    gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_NEAREST)
    gl.glEnable(gl.GL_BLEND)
    raise_on_error("after glEnable(GL_BLEND) in SetDrawMosaicState")
    gl.glBlendFunc(gl.GL_ONE, gl.GL_ZERO)
    raise_on_error("after glBlendFunc in SetDrawMosaicState")
    gl.glDepthFunc(gl.GL_LESS)
    raise_on_error("after glDepthFunc in SetDrawMosaicState")


def ClearDrawTextureState(funcs: QOpenGLFunctions):
    """Reset the GL device from drawing textures"""
    funcs.glBlendEquation(gl.GL_FUNC_ADD)
    raise_on_error("after glBlendEquation in ClearDrawTextureState")
    funcs.glClearColor(1.0, 1.0, 1.0, 1.0)
    raise_on_error("after glClearColor in ClearDrawTextureState")
    funcs.glDisable(gl.GL_BLEND)
    raise_on_error("after glDisable in ClearDrawTextureState")


def DrawTexture(texture, vertarray, texarray, verts, color=None, glFunc=gl.GL_FUNC_ADD):
    if color is None:
        color = (1.0, 1.0, 1.0, 1.0)
    gl.glBlendEquation(glFunc)
    raise_on_error("after glBlendEquation in DrawTexture")
    gl.glBindTexture(gl.GL_TEXTURE_2D, texture)
    raise_on_error("after glBindTexture in DrawTexture")
    gl.glColor4f(color[0], color[1], color[2], color[3])
    raise_on_error("after glColor4f in DrawTexture")
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
        raise_on_error("after glEnableClientState(VERTEX_ARRAY) in DrawTextureWithBuffers")
        vertex_buffer.bind()
        gl.glEnableClientState(gl.GL_INDEX_ARRAY)
        raise_on_error("after EnableClientState(INDEX_ARRAY) in DrawTextureWithBuffers")
        index_buffer.bind()
        gl.glVertexPointer(vertex_buffer)
        raise_on_error("after glVertexPointer in DrawTextureWithBuffers")
        gl.glIndexPointer(index_buffer)
        raise_on_error("after glIndexPointer in DrawTextureWithBuffers")
    finally:
        vertex_buffer.unbind()
        index_buffer.unbind()


_attribute_lookup = {}


def GetOrCreateAttribute(fmt):
    global _attribute_lookup
    if pyglet is None:
        raise RuntimeError("GetOrCreateAttribute requires pyglet")
    if fmt not in _attribute_lookup:
        attribute = pyglet.graphics.vertexattribute.create_attribute(fmt)
        _attribute_lookup[fmt] = attribute
    return _attribute_lookup[fmt]


def GetOrCreateBuffer(size: int, fmt: str, array: NDArray[numpy.floating]):
    """Generate the attributes used in the GL draw_indexed call. Legacy: uses pyglet."""
    if pyglet is None:
        raise RuntimeError("GetOrCreateBuffer requires pyglet")
    attribute = pyglet.graphics.vertexattribute.create_attribute(fmt)
    assert size == len(array) // attribute.count, f'Data for {fmt} is incorrect length'
    buffer = pyglet.graphics.vertexbuffer.create_mappable_buffer(int(size * attribute.stride), vbo=False)
    attribute.set_region(buffer, 0, int(size), array)
    attribute.enable()
    attribute.set_pointer(buffer.ptr)
    return attribute, buffer


def GetOrCreateBuffers(size: int, *data: tuple[tuple[str, numpy.ndarray], ...]):
    """Generate the attributes used in the GL draw_indexed call."""
    buffers = []
    for item in data:
        fmt, array = item
        attribute, buffer = GetOrCreateBuffer(size, fmt, array)  # type: ignore[arg-type]
        buffers.append((attribute, buffer))
    return buffers


def draw_indexed_custom(size, mode, indices, *data):
    """Draw a primitive with indexed vertices immediately. Legacy: uses pyglet."""
    if pyglet is None:
        raise RuntimeError("draw_indexed_custom requires pyglet")
    gl.glPushClientAttrib(gl.GL_CLIENT_VERTEX_ARRAY_BIT)
    raise_on_error("after glPushClientAttrib in draw_indexed_custom")
    size = int(size)
    buffers = []
    for fmt, array in data:
        attribute = GetOrCreateAttribute(fmt)
        assert size == len(array) // attribute.count, 'Data for %s is incorrect length' % fmt
        buffer = pyglet.graphics.vertexbuffer.create_mappable_buffer(size * int(attribute.stride), vbo=False)
        attribute.set_region(buffer, 0, size, array)
        attribute.enable()
        attribute.set_pointer(buffer.ptr)
        buffers.append(buffer)
    if size <= 0xff:
        index_type = gl.GL_UNSIGNED_BYTE
        index_c_type = ctypes.c_ubyte
    elif size <= 0xffff:
        index_type = gl.GL_UNSIGNED_SHORT
        index_c_type = ctypes.c_ushort
    else:
        index_type = gl.GL_UNSIGNED_INT
        index_c_type = ctypes.c_uint
    index_array = (index_c_type * len(indices))(*indices)
    gl.glDrawElements(mode, len(indices), index_type, index_array)
    raise_on_error("after glDrawElements in draw_indexed_custom")
    gl.glFlush()
    raise_on_error("after glFlush in draw_indexed_custom")
    gl.glPopClientAttrib()
    raise_on_error("after glPopClientAttrib in draw_indexed_custom")


def draw_indexed_from_buffer(size: int, vertex_buffer: vbo.VBO, index_buffer: vbo.VBO, mode: int = gl.GL_TRIANGLES):
    """Draw a primitive with indexed vertices from buffers."""
    gl.glPushClientAttrib(gl.GL_CLIENT_VERTEX_ARRAY_BIT)
    raise_on_error("after glPushClientAttrib in draw_indexed_from_buffer")
    for attribute, buffer in vertex_buffer:  # type: ignore[union-attr]
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
    index_array = (index_c_type * len(index_buffer))(*index_buffer)  # type: ignore[union-attr]
    gl.glDrawElements(mode, len(index_buffer), index_type, index_array)
    raise_on_error("after glDrawElements in draw_indexed_from_buffer")
    gl.glFlush()
    raise_on_error("after glFlush in draw_indexed_from_buffer")
    gl.glPopClientAttrib()
    raise_on_error("after glPopClientAttrib in draw_indexed_from_buffer")
