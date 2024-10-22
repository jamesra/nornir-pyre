from dependency_injector.wiring import inject, Provide
from pyre.ui.events.invoke_on_main_thread_event import wxInvokeOnMainThreadEvent, wx_EVT_INVOKE_ON_MAIN_THREAD

from pyre.interfaces.viewtype import ViewType
from pyre.interfaces.managers.window_manager import IWindowManager
from pyre.container import IContainer

try:
    import wx
    import matplotlib

    matplotlib.use('wx')
except ImportError:
    print("Ignoring wx import failure, assumed documentation use, otherwise please install wxPython")


class PyreWindowBase(wx.Frame):
    """The window we use for views"""
    _window_manager: IWindowManager

    @property
    def ID(self):
        return self._ID

    @inject
    def __init__(self,
                 parent,
                 windowID,
                 title,
                 window_manager: IWindowManager = Provide[IContainer.window_manager]):
        self._window_manager = window_manager
        wx.Frame.__init__(self, parent, title=title, size=(800, 400))

        print("Parent:" + str(self.Parent))

        # Listen for events to invoke callbacks on the main thread
        self._ID = windowID

        self.Bind(wx_EVT_INVOKE_ON_MAIN_THREAD, self._wx_invoke_on_main_thread_event_handler)

    def _wx_invoke_on_main_thread_event_handler(self, event: wxInvokeOnMainThreadEvent):
        """
        Invoke the callback on the provided event object.
        The first window to get this event should invoke the callback.
        Others should ignore it.
        """
        event.invoke()
        event.Skip()
        # obj = event.GetEventObject()
        # args, kwargs = event.GetPayload()
        # obj.invoke(*args, **kwargs)
        # event.Skip()

    def ToggleWindowShown(self):
        if self.IsShown():
            self.Hide()
        else:
            self.Show()

    def OnLeft1WindowView(self, e):
        self._window_manager[ViewType.Source.value].setPosition(position=0, desiredDisplays=1)
        self._window_manager[ViewType.Target.value].setPosition(position=0, desiredDisplays=1)
        self._window_manager[ViewType.Composite.value].setPosition(position=0, desiredDisplays=1)

    def OnCenter1WindowView(self, e):
        self._window_manager[ViewType.Source.value].setPosition(position=1, desiredDisplays=1)
        self._window_manager[ViewType.Target.value].setPosition(position=1, desiredDisplays=1)
        self._window_manager[ViewType.Composite.value].setPosition(position=1, desiredDisplays=1)

    def OnRight1WindowView(self, e):

        count = wx.Display.GetCount()

        if count == 2:
            self._window_manager[ViewType.Source.value].setPosition(position=1, desiredDisplays=1)
            self._window_manager[ViewType.Target.value].setPosition(position=1, desiredDisplays=1)
            self._window_manager[ViewType.Composite.value].setPosition(position=1, desiredDisplays=1)
        else:
            self._window_manager[ViewType.Source.value].setPosition(position=2, desiredDisplays=1)
            self._window_manager[ViewType.Target.value].setPosition(position=2, desiredDisplays=1)
            self._window_manager[ViewType.Composite.value].setPosition(position=2, desiredDisplays=1)

    def On2WindowView(self, e):
        locations = 0, 1
        self._window_manager[ViewType.Source.value].setPosition(position=locations, desiredDisplays=2)
        self._window_manager[ViewType.Target.value].setPosition(position=locations, desiredDisplays=2)
        self._window_manager[ViewType.Composite.value].setPosition(position=locations, desiredDisplays=2)

    def OnRight2WindowView(self, e):
        locations = 1, 2
        self._window_manager[ViewType.Source.value].setPosition(position=locations, desiredDisplays=2)
        self._window_manager[ViewType.Target.value].setPosition(position=locations, desiredDisplays=2)
        self._window_manager[ViewType.Composite.value].setPosition(position=locations, desiredDisplays=2)

    def On3WindowView(self, e):
        locations = 0, 1, 2
        self._window_manager[ViewType.Source.value].setPosition(position=locations, desiredDisplays=2)
        self._window_manager[ViewType.Target.value].setPosition(position=locations, desiredDisplays=2)
        self._window_manager[ViewType.Composite.value].setPosition(position=locations, desiredDisplays=2)

    def findDisplayOrder(self, position=None):

        displays = (wx.Display(i) for i in range(wx.Display.GetCount()))
        sizes = [display.GetClientArea() for display in displays]

        orderedSizeList = []
        while len(sizes) > 0:
            smallestX = None
            for i in range(len(sizes)):
                if smallestX is None:
                    smallestX = sizes[i][0], i
                if sizes[i][0] < smallestX[0]:
                    smallestX = sizes[i][0], i
            orderedSizeList.append(sizes.pop(smallestX[1]))

        return orderedSizeList

    def setPosition(self, desiredDisplays: int = None, count=None, position=None):

        if count is None:
            count = wx.Display.GetCount()
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

        ######
        # Use these for debug
        # count = 2
        # sizes = sizes[1]
        # desiredDisplays = 2
        # position = 0, 1
        ######
        if desiredDisplays == 1:
            halfX = sizes[position][2] // 2
            halfY = sizes[position][3] // 2
            if self.Title == "Fixed Image" or self.Title == self._window_manager[ViewType.Source.value].Title:
                self.Move(sizes[position][0], sizes[position][1])
                self.SetSize(halfX, halfY)
            elif self.Title == "Warped Image" or self.Title == self._window_manager[ViewType.Target.value].Title:
                self.Move(sizes[position][0] + halfX, sizes[position][1])
                self.SetSize(halfX, halfY)
            else:
                self.Move(sizes[position][0], halfY)
                self.SetSize(sizes[position][2], halfY)

        elif desiredDisplays == 2 and count >= 2:
            halfX = sizes[position[1]][2] // 2
            halfY = sizes[position[1]][3] // 2
            halfY = sizes[position[1]][3] // 2
            if self.Title == "Fixed Image" or self.Title == self._window_manager[ViewType.Source.value].Title:
                self.Move(sizes[position[1]][0], sizes[position[1]][1])
                self.SetSize(sizes[position[1]][2], halfY)
            elif self.Title == "Warped Image" or self.Title == self._window_manager[ViewType.Target.value].Title:
                self.Move(sizes[position[1]][0], halfY + sizes[position[1]][1])
                self.SetSize(sizes[position[1]][2], halfY)
            else:
                self.Move(sizes[position[0]][0], sizes[position[0]][1])
                self.SetSize(sizes[position[0]][2], sizes[position[0]][3])

        elif desiredDisplays >= 3 and count >= 3:
            if self.Title == "Fixed Image" or self.Title == self._window_manager[ViewType.Source.value].Title:
                self.Move(sizes[position[0]][0], sizes[position[0]][1])
                self.SetSize(sizes[0][2], sizes[0][3])
            elif self.Title == "Warped Image" or self.Title == self._window_manager[ViewType.Target.value].Title:
                self.Move(sizes[position[2]][0], sizes[position[2]][1])
                self.SetSize(sizes[position[2]][2], sizes[position[2]][3])
            else:
                self.Move(sizes[position[1]][0], sizes[position[1]][1])
                self.SetSize(sizes[position[1]][2], sizes[position[1]][3])
        self.Update()

    def OnClose(self, e):
        self.Shown = not self.Shown
        if not self._window_manager.any_visible_windows:
            self.OnExit()

    def OnExit(self, e=None):
        self._window_manager.exit()


if __name__ == '__main__':
    pass
