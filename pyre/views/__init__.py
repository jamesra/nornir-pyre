import ctypes

import numpy
import pyglet
from pyglet.gl import *
from pyglet.graphics import vertexbuffer, vertexattribute, vertexdomain

from compositetransformview import CompositeTransformView
import compositetransformview
from imagegridtransformview import ImageGridTransformView
from mosaicview import MosaicView
import pyglet.gl as gl
from pyre.views import imagegridtransformview
 
__all__ = ['CompositeTransformView', 'ImageGridTransformView', 'MosaicView']

 
def LineIndiciesFromTri(T):
    '''
    :param ndarray T: numpy array of triangle indicies
    :rtype: list
    :returns: 1D list of triangle indicies 
    '''
    
    LineIndicies = []

    Triangles = numpy.array(T)
    if Triangles.ndim == 1:
        Triangles = Triangles.reshape(len(Triangles) / 3, 3)

    for tri in Triangles:
        LineIndicies.append(tri[0])
        LineIndicies.append(tri[1])
        LineIndicies.append(tri[1])
        LineIndicies.append(tri[2])
        LineIndicies.append(tri[2])
        LineIndicies.append(tri[0])

    return LineIndicies


def DrawTriangles(verts, Triangles):
    LineIndicies = LineIndiciesFromTri(Triangles)

    zCoords = numpy.ones((len(verts), 1), dtype=verts.dtype)
    Points = numpy.hstack((verts, zCoords))

    FlatPoints = Points.ravel().tolist()
    vertarray = (gl.GLfloat * len(FlatPoints))(*FlatPoints)

    gl.glDisable(gl.GL_TEXTURE_2D)
    pyglet.gl.glColor4f(1.0, 0, 0, 1.0)
    pyglet.graphics.draw_indexed(len(vertarray) / 3,
                                             gl.GL_LINES,
                                             LineIndicies,
                                             ('v3f', vertarray))
    pyglet.gl.glColor4f(1.0, 1.0, 1.0, 1.0)

    
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
    '''Draw a rectangle'''
    
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
    gl.glEnable(gl.GL_TEXTURE_2D)
    gl.glDisable(gl.GL_CULL_FACE)
    gl.glEnable(GL_DEPTH_TEST)
    
    gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_S, gl.GL_CLAMP_TO_BORDER)
    gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_T, gl.GL_CLAMP_TO_BORDER)
    gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_NEAREST)
    gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_NEAREST)
    gl.glEnable(gl.GL_BLEND)
    gl.glBlendFunc(gl.GL_ONE, gl.GL_ONE)
    gl.glDepthFunc(gl.GL_LESS)

    
def SetDrawMosaicState():
    gl.glEnable(gl.GL_TEXTURE_2D)
    gl.glDisable(gl.GL_CULL_FACE)
    gl.glEnable(GL_DEPTH_TEST)
    
    gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_S, gl.GL_CLAMP_TO_BORDER)
    gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_T, gl.GL_CLAMP_TO_BORDER)
    gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_NEAREST)
    gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_NEAREST)
    gl.glEnable(gl.GL_BLEND)
    gl.glBlendFunc(gl.GL_ONE, gl.GL_ZERO)    
    gl.glDepthFunc(gl.GL_LESS)
     
    
def ClearDrawTextureState():
    '''Reset the GL device from drawing textures'''
    
    gl.glBlendEquation(gl.GL_FUNC_ADD)
    pyglet.gl.glColor4f(1.0, 1.0, 1.0, 1.0)
    gl.glDisable(gl.GL_BLEND)

    
def DrawTexture(texture, vertarray, texarray, verts, color=None, glFunc=gl.GL_FUNC_ADD):
    
    if color is None:
        color = (1.0, 1.0, 1.0, 1.0)
         
    gl.glBlendEquation(glFunc)
    gl.glBindTexture(gl.GL_TEXTURE_2D, texture)
    pyglet.gl.glColor4f(color[0], color[1], color[2], color[3])

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

    
def DrawTextureWithBuffers(texture, vertarray, buffers, verts, color=None, glFunc=gl.GL_FUNC_ADD):
    
    if color is None:
        color = (1.0, 1.0, 1.0, 1.0)
         
    gl.glBlendEquation(glFunc)
    gl.glBindTexture(gl.GL_TEXTURE_2D, texture)
    pyglet.gl.glColor4f(color[0], color[1], color[2], color[3])

#     pyglet.graphics.draw_indexed(len(vertarray) / 3,
#                                   gl.GL_TRIANGLES,
#                                   verts.tolist(),
#                                   ('v3f', vertarray),
#                                   ('t2f', texarray))
    
    draw_indexed_from_buffer(len(vertarray) / 3,
                                  gl.GL_TRIANGLES,
                                  verts.tolist(),
                                  buffers)


AttributeLookup = {}


def GetOrCreateAttribute(format):
    global AttributeLookup
    
    if not format in AttributeLookup: 
        attribute = vertexattribute.create_attribute(format)
        AttributeLookup[format] = attribute
        
    return AttributeLookup[format] 

     
def GetOrCreateBuffer(size, format, array):
    '''Generate the attributes used in the GL draw_indexed call
    ''' 
    attribute = vertexattribute.create_attribute(format)
    assert size == len(array) // attribute.count, 'Data for %s is incorrect length' % format
    
    buffer = vertexbuffer.create_mappable_buffer(size * attribute.stride, vbo=False) 
    attribute.set_region(buffer, 0, size, array)
    attribute.enable()
    attribute.set_pointer(buffer.ptr) 
         
    return (attribute, buffer)


def GetOrCreateBuffers(size, *data):
    '''Generate the attributes used in the GL draw_indexed call
    ''' 
    
    buffers = []
    for format, array in data:
        attribute, buffer = GetOrCreateBuffer(size, format, array)
        buffers.append((attribute, buffer))
        
    return buffers


def draw_indexed_custom(size, mode, indices, *data):
    '''Draw a primitive with indexed vertices immediately.

    :Parameters:
        `size` : int
            Number of vertices given
        `mode` : int
            OpenGL drawing mode, e.g. ``GL_TRIANGLES``
        `indices` : sequence of int
            Sequence of integers giving indices into the vertex list.
        `data` : data items
            Attribute formats and data.  See the module summary for details.

    '''
    glPushClientAttrib(GL_CLIENT_VERTEX_ARRAY_BIT)
    
    buffers = []
    for format, array in data:
        # #attribute = vertexattribute.create_attribute(format)
        attribute = GetOrCreateAttribute(format)
        assert size == len(array) // attribute.count, 'Data for %s is incorrect length' % format
        
        buffer = vertexbuffer.create_mappable_buffer(size * attribute.stride, vbo=False) 
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
    

def draw_indexed_from_buffer(size, mode, indices, buffers):
    '''Draw a primitive with indexed vertices immediately.

    :Parameters:
        `size` : int
            Number of vertices given
        `mode` : int
            OpenGL drawing mode, e.g. ``GL_TRIANGLES``
        `indices` : sequence of int
            Sequence of integers giving indices into the vertex list.
        `data` : data items
            Attribute formats and data.  See the module summary for details.

    '''
    glPushClientAttrib(GL_CLIENT_VERTEX_ARRAY_BIT)
    
    for attribute, buffer in buffers: 
        # attribute.enable()
        attribute.set_pointer(buffer.ptr)
         
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
    
