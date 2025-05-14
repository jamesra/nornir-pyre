import os

import wx

from pyre import state


class FileDrop(wx.FileDropTarget):
    def __init__(self, window):

        super(FileDrop, self).__init__()
        self.window = window

    def OnDragOver(self, *args, **kwargs):
        # print("DragOver")
        return wx.FileDropTarget.OnDragOver(self, *args, **kwargs)

    def OnDropFiles(self, x, y, filenames):
        for fullpath in filenames:
            try:
                dirname, filename = os.path.split(fullpath)
                root, extension = os.path.splitext(fullpath)

                if extension == ".stos":
                    state.currentStosConfig.stosdirname = dirname
                    state.currentStosConfig.stosfilename = filename
                    state.currentStosConfig.LoadStos(fullpath)
                elif extension == ".mosaic":
                    state.currentStosConfig.stosdirname = dirname
                    state.currentStosConfig.stosfilename = filename
                    state.currentStosConfig.LoadMosaic(fullpath)
                else:
                    if self.window.ID == "Fixed":
                        state.currentStosConfig.LoadFixedImage(fullpath)
                    elif self.window.ID == "Warped":
                        state.currentStosConfig.LoadWarpedImage(fullpath)
                    else:
                        pass

            except IOError as error:
                dlg = wx.MessageDialog(None, "Error opening file\n" + str(error))
                dlg.ShowModal()

        return True
