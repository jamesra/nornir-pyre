import os
from PyQt6.QtWidgets import QWidget, QMessageBox
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QDragEnterEvent, QDropEvent

from pyre import state


class FileDrop:
    """
    A helper class to add drag and drop functionality to a QWidget.
    This is not a widget itself, but rather a mixin that adds the necessary
    event handlers to an existing widget.
    """
    def __init__(self, window: QWidget):
        self.window = window
        
        # Enable drag and drop for the window
        self.window.setAcceptDrops(True)
        
        # Store the original event handlers
        self._original_dragEnterEvent = window.dragEnterEvent
        self._original_dropEvent = window.dropEvent
        
        # Override the event handlers
        window.dragEnterEvent = self.dragEnterEvent
        window.dropEvent = self.dropEvent
    
    def dragEnterEvent(self, event: QDragEnterEvent):
        """Handle drag enter events"""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        elif self._original_dragEnterEvent:
            self._original_dragEnterEvent(event)
    
    def dropEvent(self, event: QDropEvent):
        """Handle drop events"""
        if event.mimeData().hasUrls():
            filenames = [url.toLocalFile() for url in event.mimeData().urls()]
            self.processDroppedFiles(filenames)
            event.acceptProposedAction()
        elif self._original_dropEvent:
            self._original_dropEvent(event)
    
    def processDroppedFiles(self, filenames):
        """Process the dropped files"""
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
            
            except IOError as error:
                QMessageBox.critical(self.window, "Error", f"Error opening file\n{str(error)}")
        
        return True