from dependency_injector.wiring import inject, Provide
from PyQt6.QtWidgets import QMainWindow, QWidget
from PyQt6.QtCore import Qt, QEvent, QObject, pyqtSignal, QSize, QPoint
from PyQt6.QtGui import QCloseEvent

from pyre.interfaces.viewtype import ViewType
from pyre.interfaces.managers.window_manager import IWindowManager
from pyre.container import IContainer


class InvokeOnMainThreadEvent(QEvent):
    """Event for invoking callbacks on the main thread"""
    
    # Create a custom event type
    EVENT_TYPE = QEvent.Type(QEvent.Type.User + 1)
    
    def __init__(self, callback, *args, **kwargs):
        super().__init__(InvokeOnMainThreadEvent.EVENT_TYPE)
        self._callback = callback
        self._args = args
        self._kwargs = kwargs
        
    def invoke(self):
        """Invoke the callback with the provided arguments"""
        self._callback(*self._args, **self._kwargs)


class PyreWindowBase(QMainWindow):
    """The window we use for views"""
    _window_manager: IWindowManager = Provide[IContainer.window_manager]
    
    # Signal for invoking callbacks on the main thread
    invoke_on_main_thread_signal = pyqtSignal(object, tuple, dict)
    
    @property
    def ID(self):
        return self._ID
    
    @inject
    def __init__(self,
                 parent,
                 windowID,
                 title):
        super(PyreWindowBase, self).__init__(parent)
        self.setWindowTitle(title)
        self.resize(800, 400)
        
        print(f"Parent: {self.parent()}")
        
        # Store the window ID
        self._ID = windowID
        
        # Connect the signal to the slot
        self.invoke_on_main_thread_signal.connect(self._invoke_on_main_thread_handler)
        
    def event(self, event: QEvent) -> bool:
        """Handle custom events"""
        if event.type() == InvokeOnMainThreadEvent.EVENT_TYPE:
            # Handle the invoke on main thread event
            invoke_event = event
            invoke_event.invoke()
            return True
        return super().event(event)
    
    def _invoke_on_main_thread_handler(self, callback, args, kwargs):
        """Handler for the invoke_on_main_thread_signal"""
        callback(*args, **kwargs)
    
    def toggleWindowShown(self):
        """Toggle the visibility of the window"""
        if self.isVisible():
            self.hide()
        else:
            self.show()
    
    def onLeft1WindowView(self):
        """Position windows on the left display"""
        self._window_manager[ViewType.Source.value].setPosition(position=0, desiredDisplays=1)
        self._window_manager[ViewType.Target.value].setPosition(position=0, desiredDisplays=1)
        self._window_manager[ViewType.Composite.value].setPosition(position=0, desiredDisplays=1)
    
    def onCenter1WindowView(self):
        """Position windows on the center display"""
        self._window_manager[ViewType.Source.value].setPosition(position=1, desiredDisplays=1)
        self._window_manager[ViewType.Target.value].setPosition(position=1, desiredDisplays=1)
        self._window_manager[ViewType.Composite.value].setPosition(position=1, desiredDisplays=1)
    
    def onRight1WindowView(self):
        """Position windows on the right display"""
        from PyQt6.QtGui import QGuiApplication
        
        count = len(QGuiApplication.screens())
        
        if count == 2:
            self._window_manager[ViewType.Source.value].setPosition(position=1, desiredDisplays=1)
            self._window_manager[ViewType.Target.value].setPosition(position=1, desiredDisplays=1)
            self._window_manager[ViewType.Composite.value].setPosition(position=1, desiredDisplays=1)
        else:
            self._window_manager[ViewType.Source.value].setPosition(position=2, desiredDisplays=1)
            self._window_manager[ViewType.Target.value].setPosition(position=2, desiredDisplays=1)
            self._window_manager[ViewType.Composite.value].setPosition(position=2, desiredDisplays=1)
    
    def on2WindowView(self):
        """Position windows across two displays"""
        locations = 0, 1
        self._window_manager[ViewType.Source.value].setPosition(position=locations, desiredDisplays=2)
        self._window_manager[ViewType.Target.value].setPosition(position=locations, desiredDisplays=2)
        self._window_manager[ViewType.Composite.value].setPosition(position=locations, desiredDisplays=2)
    
    def onRight2WindowView(self):
        """Position windows across the right two displays"""
        locations = 1, 2
        self._window_manager[ViewType.Source.value].setPosition(position=locations, desiredDisplays=2)
        self._window_manager[ViewType.Target.value].setPosition(position=locations, desiredDisplays=2)
        self._window_manager[ViewType.Composite.value].setPosition(position=locations, desiredDisplays=2)
    
    def on3WindowView(self):
        """Position windows across three displays"""
        locations = 0, 1, 2
        self._window_manager[ViewType.Source.value].setPosition(position=locations, desiredDisplays=2)
        self._window_manager[ViewType.Target.value].setPosition(position=locations, desiredDisplays=2)
        self._window_manager[ViewType.Composite.value].setPosition(position=locations, desiredDisplays=2)
    
    def findDisplayOrder(self, position=None):
        """Find the order of displays based on their x-coordinates"""
        from PyQt6.QtGui import QGuiApplication
        
        screens = QGuiApplication.screens()
        sizes = [screen.availableGeometry() for screen in screens]
        
        orderedSizeList = []
        sizes_copy = sizes.copy()
        
        while len(sizes_copy) > 0:
            smallestX = None
            for i in range(len(sizes_copy)):
                if smallestX is None:
                    smallestX = sizes_copy[i].x(), i
                if sizes_copy[i].x() < smallestX[0]:
                    smallestX = sizes_copy[i].x(), i
            orderedSizeList.append(sizes_copy.pop(smallestX[1]))
        
        return orderedSizeList
    
    def setPosition(self, desiredDisplays: int = None, count=None, position=None):
        """Set the position of the window based on the available displays"""
        from PyQt6.QtGui import QGuiApplication
        
        if count is None:
            count = len(QGuiApplication.screens())
        if desiredDisplays is None:
            desiredDisplays = count
        if position is None:
            if count == 1:
                position = 0
            elif count == 2:
                position = 0, 1
            else:
                position = 0, 1, 2
        
        sizes = self.findDisplayOrder(position)
        
        if ViewType.Source.value not in self._window_manager:
            return
        
        if ViewType.Target.value not in self._window_manager:
            return
        
        if desiredDisplays == 1:
            halfX = sizes[position].width() // 2
            halfY = sizes[position].height() // 2
            if self.windowTitle() == "Fixed Image" or self.windowTitle() == self._window_manager[ViewType.Source.value].windowTitle():
                self.move(sizes[position].x(), sizes[position].y())
                self.resize(halfX, halfY)
            elif self.windowTitle() == "Warped Image" or self.windowTitle() == self._window_manager[ViewType.Target.value].windowTitle():
                self.move(sizes[position].x() + halfX, sizes[position].y())
                self.resize(halfX, halfY)
            else:
                self.move(sizes[position].x(), halfY)
                self.resize(sizes[position].width(), halfY)
        
        elif desiredDisplays == 2 and count >= 2:
            halfX = sizes[position[1]].width() // 2
            halfY = sizes[position[1]].height() // 2
            if self.windowTitle() == "Fixed Image" or self.windowTitle() == self._window_manager[ViewType.Source.value].windowTitle():
                self.move(sizes[position[1]].x(), sizes[position[1]].y())
                self.resize(sizes[position[1]].width(), halfY)
            elif self.windowTitle() == "Warped Image" or self.windowTitle() == self._window_manager[ViewType.Target.value].windowTitle():
                self.move(sizes[position[1]].x(), halfY + sizes[position[1]].y())
                self.resize(sizes[position[1]].width(), halfY)
            else:
                self.move(sizes[position[0]].x(), sizes[position[0]].y())
                self.resize(sizes[position[0]].width(), sizes[position[0]].height())
        
        elif desiredDisplays >= 3 and count >= 3:
            if self.windowTitle() == "Fixed Image" or self.windowTitle() == self._window_manager[ViewType.Source.value].windowTitle():
                self.move(sizes[position[0]].x(), sizes[position[0]].y())
                self.resize(sizes[0].width(), sizes[0].height())
            elif self.windowTitle() == "Warped Image" or self.windowTitle() == self._window_manager[ViewType.Target.value].windowTitle():
                self.move(sizes[position[2]].x(), sizes[position[2]].y())
                self.resize(sizes[position[2]].width(), sizes[position[2]].height())
            else:
                self.move(sizes[position[1]].x(), sizes[position[1]].y())
                self.resize(sizes[position[1]].width(), sizes[position[1]].height())
        self.update()
    
    def closeEvent(self, event: QCloseEvent):
        """Handle the close event"""
        self.setVisible(not self.isVisible())
        if not self._window_manager.any_visible_windows:
            self.onExit()
        event.ignore()  # Don't actually close the window, just hide it
    
    def onExit(self):
        """Exit the application"""
        self._window_manager.exit()


if __name__ == '__main__':
    pass