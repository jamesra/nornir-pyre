from PyQt6.QtCore import QEvent
from PyQt6.QtGui import QOpenGLContext


class QtGLContextCreatedEvent(QEvent):
    """A Qt event that is sent when a new GL context is created so GL objects can be created in that context"""
    # Create a custom event type
    EVENT_TYPE = QEvent.Type(QEvent.Type.User + 2)

    _context: QOpenGLContext

    @property
    def context(self) -> QOpenGLContext:
        return self._context

    def __init__(self, context: QOpenGLContext):
        super().__init__(QtGLContextCreatedEvent.EVENT_TYPE)
        self._context = context
