import wx
from . import command_base
from pyre.viewmodels import TransformController
import pyre.views.controlpoint_view
from pyre.gl_engine.gl_buffer import GLBuffer
from pyre.state import ITransformControllerGLBufferManager, GLBufferCollection, BufferType


class DefaultStosCommand(command_base.CommandBase):
    """
    Supports:
     1. Navigating around the view of the images.
     2. Selecting control points
    """

    _last_mouse_position: wx.Point
    _control_point_view: pyre.views.controlpoint_view.ControlPointView
    _transform_controller: TransformController  # The transform controller for the control points we are manipulating
    _control_points_buffer: GLBuffer
    _selected_points_buffer: GLBuffer

    def __init__(self, parent: wx.Window,
                 transform_controller: TransformController,
                 glbuffer_manager: pyre.state.ITransformControllerGLBufferManager):
        self._transform_controller = transform_controller
        self._control_points_buffer = glbuffer_manager.get_glbuffer(transform_controller, BufferType.ControlPoint)
        self._selected_points_buffer = glbuffer_manager.get_glbuffer(transform_controller, BufferType.Selection)
        self._transform_controller.AddOnChangeEventListener(self.on_transform_changed)
        super().__init__(parent)

    def on_mouse_scroll(self, event_data):
        pass

    def on_mouse_press(self, event_data):
        pass

    def on_mouse_drag(self, event_data):
        pass

    def on_mouse_release(self, event_data):
        pass

    def on_key_down(self, event_data):
        pass

    def __del__(self):
        self._transform_controller.RemoveOnChangeEventListener(self.on_transform_changed)
