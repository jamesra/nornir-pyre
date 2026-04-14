import os
from PyQt6.QtWidgets import QWidget, QMessageBox
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QDragEnterEvent, QDropEvent

from pyre import state
from pyre.interfaces.viewtype import ViewType


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
        window.dragEnterEvent = self.dragEnterEvent  # type: ignore[method-assign]
        window.dropEvent = self.dropEvent  # type: ignore[method-assign]

    def dragEnterEvent(self, event: QDragEnterEvent):
        """Handle drag enter events"""
        mime = event.mimeData()
        if mime is not None and mime.hasUrls():
            event.acceptProposedAction()
        elif self._original_dragEnterEvent:
            self._original_dragEnterEvent(event)

    def dropEvent(self, event: QDropEvent):
        """Handle drop events"""
        mime = event.mimeData()
        if mime is not None and mime.hasUrls():
            filenames = [url.toLocalFile() for url in mime.urls()]
            self.processDroppedFiles(filenames)
            event.acceptProposedAction()
        elif self._original_dropEvent:
            self._original_dropEvent(event)
        return
    
    def processDroppedFiles(self, filenames):
        """Process the dropped files"""
        config = state.get_current_stos_config()
        if config is None:
            QMessageBox.warning(self.window, "Not ready", "No STOS session is active.")
            return True
        for fullpath in filenames:
            try:
                dirname, filename = os.path.split(fullpath)
                root, extension = os.path.splitext(fullpath)
                
                if extension == ".stos":
                    config.stosdirname = dirname
                    config.stosfilename = filename
                    config.LoadStos(fullpath)  # type: ignore[attr-defined]
                elif extension == ".mosaic":
                    config.stosdirname = dirname
                    config.stosfilename = filename
                    config.LoadMosaic(fullpath)  # type: ignore[attr-defined]
                else:
                    # Prefer ViewType (StosWindow has _view_type or ID); fallback to legacy string ID
                    view_type = getattr(self.window, '_view_type', None) or getattr(self.window, 'ID', None)
                    if view_type in (ViewType.Source, ViewType.Fixed) or self.window.ID == "Fixed":  # type: ignore[attr-defined]
                        config.LoadFixedImage(fullpath)
                    elif view_type in (ViewType.Target, ViewType.Warped) or self.window.ID == "Warped":  # type: ignore[attr-defined]
                        config.LoadWarpedImage(fullpath)
            
            except IOError as error:
                QMessageBox.critical(self.window, "Error", f"Error opening file\n{str(error)}")
        
        return True