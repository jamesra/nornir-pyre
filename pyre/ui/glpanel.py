#!/usr/bin/python
import os
import sys

from pyglet import gl
import pyglet
    
from wx import glcanvas
import wx

pyglet.options['shadow_window'] = False


class GLPanel(wx.Panel):

    '''A simple class for using OpenGL with wxPython.'''

    pygletcontext = None
    wxcontext = None

    def __init__(self, parent, window_id, pos=wx.DefaultPosition,
                 size=wx.DefaultSize, style=0):
        # Forcing a no full repaint to stop flickering
        style = style | wx.NO_FULL_REPAINT_ON_RESIZE
        # call super function
        super(GLPanel, self).__init__(parent, window_id, pos, size, style)

        # init gl canvas data
        self.GLinitialized = False
        attribList = (glcanvas.WX_GL_RGBA,  # RGBA
                      glcanvas.WX_GL_DOUBLEBUFFER,  # Double Buffered
                      glcanvas.WX_GL_DEPTH_SIZE, 32)  # 24 bit

        # Create context
        if GLPanel.wxcontext is None:
            GLPanel.pygletcontext = gl.Context(gl.current_context)
            self.canvas = glcanvas.GLCanvas(self, attribList=attribList)
            GLPanel.wxcontext = self.canvas.GetContext()
        else:
            self.canvas = glcanvas.GLCanvasWithContext(self, shared=GLPanel.wxcontext, attribList=attribList)

        # Create the canvas

        self.sizer = wx.BoxSizer(wx.VERTICAL)

        self.sizer.Add(self.canvas, 1, wx.EXPAND)
        self.SetSizer(self.sizer)
        self.sizer.Fit(self)
        self.Layout()

        # bind events
        self.canvas.Bind(wx.EVT_ERASE_BACKGROUND, self.processEraseBackgroundEvent)
        self.canvas.Bind(wx.EVT_SIZE, self.processSizeEvent)
        self.canvas.Bind(wx.EVT_PAINT, self.processPaintEvent)

    #==========================================================================
    # Canvas Proxy Methods
    #==========================================================================
    def GetGLExtents(self):
        '''Get the extents of the OpenGL canvas.'''
        return self.canvas.GetClientSize()

    def SwapBuffers(self):
        '''Swap the OpenGL buffers.'''
        self.canvas.SwapBuffers()

    #==========================================================================
    # wxPython Window Handlers
    #==========================================================================
    def processEraseBackgroundEvent(self, event):
        '''Process the erase background event.'''
        pass  # Do nothing, to avoid flashing on MSWin

    def processSizeEvent(self, event):
        '''Process the resize event.'''
        if self.canvas.GetContext():
            # Make sure the frame is shown before calling SetCurrent.
            self.Show()
            self.canvas.SetCurrent()
            size = self.GetGLExtents()
            self.winsize = (size.width, size.height)
            self.width, self.height = size.width, size.height
            self.OnReshape(size.width, size.height)
            self.canvas.Refresh(False)
        event.Skip()

    def processPaintEvent(self, event):
        '''Process the drawing event.'''
        self.canvas.SetCurrent()

        # This is a 'perfect' time to initialize OpenGL ... only if we need to
        if not self.GLinitialized:
            self.OnInitGL()

        self.OnDraw()
        event.Skip()

    def Destroy(self):
        # clean up the pyglet OpenGL context
        # GLPanel.pygletcontext.destroy()
        # call the super method
        super(GLPanel, self).Destroy()

    #==========================================================================
    # GLFrame OpenGL Event Handlers
    #==========================================================================
    def OnInitGL(self):
        '''Initialize OpenGL for use in the window.'''
        # create a pyglet context for this panel

        if self.GLinitialized:
            return

        GLPanel.pygletcontext = gl.Context(gl.current_context)
        GLPanel.pygletcontext.canvas = self

        GLPanel.pygletcontext.set_current()

        # normal gl init
        self._InitGLState()

        # create objects to draw
        self.create_objects()

        self.GLinitialized = True
        
    def _InitGLState(self):
        gl.glEnable(gl.GL_BLEND)
        gl.glBlendFunc(gl.GL_ONE, gl.GL_ONE)
        gl.glEnable(gl.GL_TEXTURE_2D)
        gl.glShadeModel(gl.GL_SMOOTH)
        gl.glClearColor(0, 0, 0, 1)
        # Rotated images can have a z-distance of more than one
        gl.glDepthRangef(0, 2)

    def OnReshape(self, width, height):
        '''Reshape the OpenGL viewport based on the dimensions of the window.'''

        # Zero values occasionally appear during window setup.  Ignore these until real values appear
        if width == 0 or height == 0:
            return

        if not self.GLinitialized:
            self.OnInitGL()

        gl.glViewport(0, 0, width, height)
        gl.glMatrixMode(gl.GL_PROJECTION)
        gl.glLoadIdentity()
        gl.glOrtho(0, width, 0, height, 1, -1)
        gl.glMatrixMode(gl.GL_MODELVIEW)
        # pyglet stuff

        # Wrap text to the width of the window
        if self.GLinitialized:
            GLPanel.pygletcontext.set_current()
            self.update_object_resize()

    def OnDraw(self, *args, **kwargs):
        """Draw the window."""
        # clear the context
        if not self.IsShown():
            return

        self.canvas.SetCurrent()
        GLPanel.pygletcontext.set_current()
        gl.glClear(gl.GL_COLOR_BUFFER_BIT | gl.GL_DEPTH_BUFFER_BIT)
        # draw objects
        self.draw_objects()
        # update screen
        self.SwapBuffers()

    #==========================================================================
    # To be implamented by a sub class
    #==========================================================================
    def create_objects(self):
        '''create opengl objects when opengl is initialized'''
        pass

    def update_object_resize(self):
        '''called when the window recieves only if opengl is initialized'''
        pass

    def draw_objects(self):
        '''called in the middle of ondraw after the buffer has been cleared'''
        pass


class TestGlPanel(GLPanel):

    def __init__(self, parent, window_id=wx.ID_ANY, pos=(10, 10)):
        super(TestGlPanel, self).__init__(parent, window_id, wx.DefaultPosition, wx.DefaultSize, 0)
        self.spritepos = pos

    def create_objects(self):
        '''create opengl objects when opengl is initialized'''
        FOO_IMAGE = pyglet.image.load('foo.png')
        self.batch = pyglet.graphics.Batch()
        self.sprite = pyglet.sprite.Sprite(FOO_IMAGE, batch=self.batch)
        self.sprite.x = self.spritepos[0]
        self.sprite.y = self.spritepos[1]
        self.sprite2 = pyglet.sprite.Sprite(FOO_IMAGE, batch=self.batch)
        self.sprite2.x = self.spritepos[0] + 100
        self.sprite2.y = self.spritepos[1] + 200

    def update_object_resize(self):
        '''called when the window recieves only if opengl is initialized'''
        pass

    def draw_objects(self):
        '''called in the middle of ondraw after the buffer has been cleared'''
        self.batch.draw()


class TestFrame(wx.Frame):
    '''A simple class for using OpenGL with wxPython.'''

    def __init__(self, parent, ID, title, pos=wx.DefaultPosition,
            size=wx.DefaultSize, style=wx.DEFAULT_FRAME_STYLE):
        super(TestFrame, self).__init__(parent, ID, title, pos, size, style)

        self.mainsizer = wx.BoxSizer(wx.HORIZONTAL)
        self.GLPanel1 = TestGlPanel(self)
        self.mainsizer.Add(self.GLPanel1, 1, wx.EXPAND)
        self.GLPanel2 = TestGlPanel(self, wx.ID_ANY, (20, 20))
        self.mainsizer.Add(self.GLPanel2, 1, wx.EXPAND)

	print "init process"
        self.SetSizer(self.mainsizer)
        # self.mainsizer.Fit(self)
        self.Layout()


if __name__ == '__main__':
    app = wx.App(redirect=False)
    # frame = TestFrame(None, wx.ID_ANY, 'GL Window', size=(400,400))
    frame = wx.Frame(None, -1, "GL Window", size=(400, 400))
    panel = TestGlPanel(frame)
    print "show"
    frame.Show(True)
    print "main loop"
    app.MainLoop()
    app.Destroy()
