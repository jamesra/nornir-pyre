import wx


class TextDrop(wx.TextDropTarget):
    def __init__(self, window):
        super(TextDrop, self).__init__()
        self.window = window

    def OnDragOver(self, *args, **kwargs):
        print("DragOver Text")
        return wx.TextDropTarget.OnDragOver(self, *args, **kwargs)

    def OnDropText(self, x, y, data):
        print(str(data))
