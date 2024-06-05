import wx
import abc
from abc import abstractmethod


class CommandBase(abc.ABC):
    """
    Supports:
     1. Navigating around the view of the image.
     2. Selecting control points
    """

    _parent: wx.Window

    def __init__(self, parent: wx.Window):
        self._parent = parent
        self._bind_mouse_events()
        self._bind_key_events()

    def _bind_mouse_events(self):
        self._parent.Bind(wx.EVT_MOUSEWHEEL, self.on_mouse_scroll)
        self._parent.Bind(wx.EVT_LEFT_DOWN, self.on_mouse_press)
        self._parent.Bind(wx.EVT_MIDDLE_DOWN, self.on_mouse_press)
        self._parent.Bind(wx.EVT_RIGHT_DOWN, self.on_mouse_press)
        self._parent.Bind(wx.EVT_MOTION, self.on_mouse_drag)
        self._parent.Bind(wx.EVT_LEFT_UP, self.on_mouse_release)

    def _bind_key_events(self):
        self._parent.Bind(wx.EVT_KEY_DOWN, self.on_key_down)

    @abstractmethod
    def on_mouse_scroll(self, event_data):
        raise NotImplementedError()

    @abstractmethod
    def on_mouse_press(self, event_data):
        raise NotImplementedError()

    @abstractmethod
    def on_mouse_drag(self, event_data):
        raise NotImplementedError()

    @abstractmethod
    def on_mouse_release(self, event_data):
        raise NotImplementedError()

    @abstractmethod
    def on_key_down(self, event_data):
        raise NotImplementedError()
