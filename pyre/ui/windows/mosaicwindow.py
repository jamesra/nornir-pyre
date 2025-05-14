import os

import wx

import pyre
from pyre import state
from pyre.ui.windows.pyrewindows import PyreWindowBase


class MosaicWindow(PyreWindowBase):
    '''The window which we use for mosaic views'''
    mosaicfilename = ''

    def __init__(self, parent, windowID, title):

        super(MosaicWindow, self).__init__(parent=parent, windowID=windowID, title=title)

        self.mosaicpanel = pyre.ui.MosaicTransformPanel(parent=self,
                                                        imageTransformViewList=None)

        self.CreateMenu()

        self.Show(True)
        self.setPosition()

    def CreateMenu(self):

        menuBar = wx.MenuBar()

        filemenu = self.__CreateFileMenu()
        menuBar.Append(filemenu, "&File")

        self.SetMenuBar(menuBar)

        self.Bind(wx.EVT_CLOSE, self.OnClose)

    def __CreateFileMenu(self):

        filemenu = wx.Menu()

        menuOpenMosaic = filemenu.Append(wx.ID_ANY, "&Open mosaic file")
        self.Bind(wx.EVT_MENU, self.OnOpenMosaic, menuOpenMosaic)

        filemenu.AppendSeparator()

        menuSaveMosaic = filemenu.Append(wx.ID_ANY, "&Save mosaic file")
        self.Bind(wx.EVT_MENU, self.OnSaveMosaic, menuSaveMosaic)

        filemenu.AppendSeparator()

        menuExit = filemenu.Append(wx.ID_EXIT, "&Exit")
        self.Bind(wx.EVT_MENU, self.OnExit, menuExit)

        return filemenu

    def OnOpenMosaic(self, e):
        self.dirname = ''
        dlg = wx.FileDialog(self, "Choose a file", self.dirname, "", "*.mosaic", wx.OPEN)
        if dlg.ShowModal() == wx.ID_OK:
            filename = str(dlg.GetFilename())
            dirname = str(dlg.GetDirectory())
            MosaicWindow.mosaicfilename = filename

            ImageTransformViewList = state.currentMosaicConfig.LoadMosaic(os.path.join(dirname, filename))
            if ImageTransformViewList is None:
                # Prompt for UI to choose tiles directory
                tiles_dir_dlg = wx.DirDialog(self, "Choose the directory containing the tiles for the mosaic file",
                                             dirname, name="Tile directory")
                if tiles_dir_dlg.ShowModal() == wx.ID_OK:
                    ImageTransformViewList = state.currentMosaicConfig.LoadMosaic(os.path.join(dirname, filename),
                                                                                  tiles_dir=tiles_dir_dlg.Path)

            self.mosaicpanel.ImageTransformViewList = ImageTransformViewList

        dlg.Destroy()

    def OnSaveMosaic(self, e):
        pass
