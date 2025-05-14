import os

from PyQt6.QtWidgets import QMessageBox
from PyQt6.QtCore import QObject

from pyre import state
from pyre.interfaces.viewtype import ViewType


class FileDrop(QObject):
    def __init__(self, window):
        super(FileDrop, self).__init__()
        self.window = window

        # Enable drag and drop for the window
        self.window.setAcceptDrops(True)

        # Store the original event handlers
        self._original_dragEnterEvent = window.dragEnterEvent
        self._original_dropEvent = window.dropEvent

        # Override the event handlers
        window.dragEnterEvent = self._dragEnterEvent
        window.dropEvent = self._dropEvent

    def _dragEnterEvent(self, event):
        """Handle drag enter events"""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        elif self._original_dragEnterEvent:
            self._original_dragEnterEvent(event)

    def _dropEvent(self, event):
        """Handle drop events"""
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            filenames = [url.toLocalFile() for url in urls]
            self.onDropFiles(event.position().x(), event.position().y(), filenames)
            event.acceptProposedAction()
        elif self._original_dropEvent:
            self._original_dropEvent(event)

    def onDropFiles(self, x, y, filenames):
        """Handle dropped files"""
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
                    if self.window.ID == ViewType.Source:
                        state.currentStosConfig.LoadFixedImage(fullpath)
                    elif self.window.ID == ViewType.Target:
                        state.currentStosConfig.LoadWarpedImage(fullpath)
                    else:
                        pass

            except IOError as error:
                dlg = QMessageBox(self.window)
                dlg.setWindowTitle("Error")
                dlg.setText(f"Error opening file\n{error}")
                dlg.setStandardButtons(QMessageBox.StandardButton.Ok)
                dlg.exec()

        return True
