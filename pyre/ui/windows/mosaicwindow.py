import os

from PyQt6.QtWidgets import QMenu, QMenuBar, QFileDialog
from PyQt6.QtCore import Qt

import pyre
from pyre import state
from pyre.ui.windows.pyrewindows import PyreWindowBase


class MosaicWindow(PyreWindowBase):
    '''The window which we use for mosaic views'''
    mosaicfilename = ''

    def __init__(self, parent, windowID, title):
        super(MosaicWindow, self).__init__(parent=parent, windowID=windowID, title=title)

        # Create the mosaic panel
        self.mosaicpanel = pyre.ui.widgets.MosaicTransformPanel(parent=self,
                                                                imageTransformViewList=None)

        # Set the mosaic panel as the central widget
        self.setCentralWidget(self.mosaicpanel)

        # Create menu
        self.createMenu()

        # Show the window and set position
        self.show()
        self.setPosition()

    def createMenu(self):
        """Create the menu bar and menus"""
        menuBar = QMenuBar(self)
        self.setMenuBar(menuBar)

        # Create File menu
        filemenu = self.__createFileMenu()
        menuBar.addMenu(filemenu)

    def __createFileMenu(self):
        """Create the File menu"""
        filemenu = QMenu("&File", self)

        # Open mosaic action
        menuOpenMosaic = filemenu.addAction("&Open mosaic file")
        menuOpenMosaic.triggered.connect(self.onOpenMosaic)

        filemenu.addSeparator()

        # Save mosaic action
        menuSaveMosaic = filemenu.addAction("&Save mosaic file")
        menuSaveMosaic.triggered.connect(self.onSaveMosaic)

        filemenu.addSeparator()

        # Exit action
        menuExit = filemenu.addAction("&Exit")
        menuExit.triggered.connect(self.onExit)

        return filemenu

    def onOpenMosaic(self):
        """Handle Open mosaic file action"""
        self.dirname = ''

        # Create file dialog
        dialog = QFileDialog(self)
        dialog.setWindowTitle("Choose a file")
        dialog.setNameFilter("Mosaic files (*.mosaic)")
        dialog.setFileMode(QFileDialog.FileMode.ExistingFile)

        if dialog.exec() == QFileDialog.DialogCode.Accepted:
            # Get selected file
            selected_files = dialog.selectedFiles()
            if selected_files:
                filepath = selected_files[0]
                filename = os.path.basename(filepath)
                dirname = os.path.dirname(filepath)
                MosaicWindow.mosaicfilename = filename

                # Load mosaic
                ImageTransformViewList = state.currentMosaicConfig.LoadMosaic(filepath)
                if ImageTransformViewList is None:
                    # Prompt for UI to choose tiles directory
                    tiles_dir_dialog = QFileDialog(self)
                    tiles_dir_dialog.setWindowTitle("Choose the directory containing the tiles for the mosaic file")
                    tiles_dir_dialog.setDirectory(dirname)
                    tiles_dir_dialog.setFileMode(QFileDialog.FileMode.Directory)

                    if tiles_dir_dialog.exec() == QFileDialog.DialogCode.Accepted:
                        selected_dirs = tiles_dir_dialog.selectedFiles()
                        if selected_dirs:
                            tiles_dir = selected_dirs[0]
                            ImageTransformViewList = state.currentMosaicConfig.LoadMosaic(filepath, tiles_dir=tiles_dir)

                # Set the image transform view list
                self.mosaicpanel.ImageTransformViewList = ImageTransformViewList

    def onSaveMosaic(self):
        """Handle Save mosaic file action"""
        pass
