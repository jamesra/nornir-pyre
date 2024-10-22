import sys

try:
    import wx
except:
    print("Ignoring wx import failure, assumed documentation use, otherwise please install wxPython")

if not hasattr(sys, 'frozen'):
    import wxversion

    print("Wx version: " + str(wxversion.getInstalled()))
    wxversion.select('2.8')

print("Python version: " + sys.version)


class TestWxDrop(wx.Frame):

    def __init__(self, parent):
        '''
        Constructor
        '''
        wx.Frame.__init__(self, parent, title="Test file drop window", size=(400, 200))

        self.SetDropTarget(FileDrop(self))

        self.Show()


class FileDrop(wx.FileDropTarget):

    def __init__(self, window):
        super(FileDrop, self).__init__()
        self.window = window

    def OnDragOver(self, *args, **kwargs):
        print("DragOver")
        return wx.FileDropTarget.OnDragOver(self, *args, **kwargs)

    def OnDropFiles(self, x, y, filenames):
        print("You dropped a file! " + str(filenames))


if __name__ == "__main__":
    app = wx.App(False)

    window = TestWxDrop(parent=None)

    app.TopWindow = window

    app.MainLoop()
