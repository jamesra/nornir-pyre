from dependency_injector.wiring import Provide
from typing import cast
from PyQt6.QtWidgets import QMainWindow, QWidget, QApplication
from PyQt6.QtCore import Qt, QEvent, QObject, pyqtSignal, QSize, QPoint
from PyQt6.QtGui import QCloseEvent

from pyre.interfaces.viewtype import ViewType
from pyre.interfaces.managers.window_manager import IWindowManager
from pyre.container import IContainer

# View types that have layout windows (Source, Target, Composite)
_LAYOUT_VIEW_TYPES = (ViewType.Source, ViewType.Target, ViewType.Composite)


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
            invoke_event = cast(InvokeOnMainThreadEvent, event)
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
    
    def _set_layout_position(self, position, desired_displays: int = 1, layout_mode: str | None = None):
        """Call setPosition on each layout window that exists in the manager (avoids KeyError if not yet registered)."""
        # Collect windows: support both ViewType keys (Source/Target/Composite) and legacy (Fixed/Warped/Composite)
        to_position = []
        for view_type in _LAYOUT_VIEW_TYPES:
            if view_type in self._window_manager:
                to_position.append(self._window_manager[view_type])
        if len(to_position) < 3:
            to_position = []
            for key in ("Fixed", "Warped", "Composite"):
                if key in self._window_manager:
                    to_position.append(self._window_manager[key])
        for win in to_position:
            win.setPosition(position=position, desiredDisplays=desired_displays, layout_mode=layout_mode)

    def onLeft1WindowView(self):
        """Position windows on the left display"""
        self._set_layout_position(0, desired_displays=1)
    
    def onCenter1WindowView(self):
        """Position windows on the center display"""
        self._set_layout_position(1, desired_displays=1)
    
    def onRight1WindowView(self):
        """Position windows on the right display (or only display if single monitor)"""
        from PyQt6.QtGui import QGuiApplication
        count = len(QGuiApplication.screens())
        position = 0 if count == 1 else (1 if count == 2 else 2)
        self._set_layout_position(position, desired_displays=1)
    
    def on2WindowView(self):
        """Position windows across two displays"""
        self._set_layout_position((0, 1), desired_displays=2)
    
    def onRight2WindowView(self):
        """Position windows across the right two displays"""
        self._set_layout_position((1, 2), desired_displays=2)
    
    def on3WindowView(self):
        """Position windows across three displays"""
        self._set_layout_position((0, 1, 2), desired_displays=2)
    
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
            assert smallestX is not None
            orderedSizeList.append(sizes_copy.pop(smallestX[1]))
        
        return orderedSizeList
    
    def setPosition(self, desiredDisplays: int | None = None, count: int | None = None,
                    position: int | tuple[int, int] | tuple[int, int, int] | None = None,
                    layout_mode: str | None = None):
        """Set the position of the window based on the available displays."""
        del layout_mode  # subclasses (StosWindow) handle special layout modes before tiling
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
        
        # Resolve actual manager keys (launcher may use ViewType.Source->"Source" or legacy "Fixed"/"Warped")
        source_key = "Source" if ViewType.Source in self._window_manager else ("Fixed" if "Fixed" in self._window_manager else None)
        target_key = "Target" if ViewType.Target in self._window_manager else ("Warped" if "Warped" in self._window_manager else None)
        if source_key is None or target_key is None:
            return

        try:
            source_win = self._window_manager[source_key]
            target_win = self._window_manager[target_key]
        except KeyError:
            raise
        # Identify this window by object identity so layout works regardless of title
        is_source = self is source_win
        is_target = self is target_win
        
        if desiredDisplays == 1:
            p0 = cast(int, position)
            halfX = sizes[p0].width() // 2
            halfY = sizes[p0].height() // 2
            if is_source:
                self.move(sizes[p0].x(), sizes[p0].y())
                self.resize(halfX, halfY)
            elif is_target:
                self.move(sizes[p0].x() + halfX, sizes[p0].y())
                self.resize(halfX, halfY)
            else:
                self.move(sizes[p0].x(), sizes[p0].y() + halfY)
                self.resize(sizes[p0].width(), halfY)
        
        elif desiredDisplays == 2 and count >= 2:
            p2 = cast(tuple[int, int], position)
            halfX = sizes[p2[1]].width() // 2
            halfY = sizes[p2[1]].height() // 2
            if is_source:
                self.move(sizes[p2[1]].x(), sizes[p2[1]].y())
                self.resize(sizes[p2[1]].width(), halfY)
            elif is_target:
                self.move(sizes[p2[1]].x(), halfY + sizes[p2[1]].y())
                self.resize(sizes[p2[1]].width(), halfY)
            else:
                self.move(sizes[p2[0]].x(), sizes[p2[0]].y())
                self.resize(sizes[p2[0]].width(), sizes[p2[0]].height())
        
        elif desiredDisplays >= 3 and count >= 3:
            p3 = cast(tuple[int, int, int], position)
            if is_source:
                self.move(sizes[p3[0]].x(), sizes[p3[0]].y())
                self.resize(sizes[p3[0]].width(), sizes[p3[0]].height())
            elif is_target:
                self.move(sizes[p3[2]].x(), sizes[p3[2]].y())
                self.resize(sizes[p3[2]].width(), sizes[p3[2]].height())
            else:
                self.move(sizes[p3[1]].x(), sizes[p3[1]].y())
                self.resize(sizes[p3[1]].width(), sizes[p3[1]].height())
        self.update()
    
    def closeEvent(self, event: QCloseEvent):
        """Handle the close event"""
        # Hide the window (don't toggle - if it's being closed, hide it)
        self.hide()
        
        # Check if all windows are now hidden
        if not self._window_manager.any_visible_windows:
            # All windows are hidden, exit the application
            self.onExit()
            event.accept()  # Accept the close event to allow application to exit
        else:
            # Other windows are still visible, just hide this one
            event.accept()  # Accept the close event (window is hidden, not destroyed)
    
    def onExit(self):
        """Close managed windows and end the Qt event loop."""
        self._window_manager.exit()
        app = QApplication.instance()
        if app is not None:
            app.quit()


if __name__ == '__main__':
    pass