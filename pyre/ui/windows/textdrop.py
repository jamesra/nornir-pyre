from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QDragEnterEvent, QDropEvent


class TextDrop:
    """
    A helper class to add text drag and drop functionality to a QWidget.
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
        if mime is not None and mime.hasText():
            print("DragOver Text")
            event.acceptProposedAction()
        elif self._original_dragEnterEvent:
            self._original_dragEnterEvent(event)
    
    def dropEvent(self, event: QDropEvent):
        """Handle drop events"""
        mime = event.mimeData()
        if mime is not None and mime.hasText():
            text = mime.text()
            print(str(text))
            event.acceptProposedAction()
        elif self._original_dropEvent:
            self._original_dropEvent(event)