import abc
import enum
import numpy as np
from numpy.typing import NDArray
import OpenGL.GL as gl
from dataclasses import dataclass
from pyre.gl_engine.gl_buffer import GLBuffer
from pyre.gl_engine.vertexarraylayout import VertexArrayLayout
import nornir_imageregistration
from nornir_imageregistration import ITransform
import pyre.viewmodels
from pyre.viewmodels.transformcontroller import TransformController
from pyre.state.gl_context_manager import IGLContextManager
from .events import TransformControllerAddRemoveCallback
from . import Action
from pyre.interfaces import IEventManager
from pyre.state.eventmanager import wxEventManager


class BufferType(enum.IntEnum):
    """The type of buffer to return"""
    ControlPoint = 1
    Selection = 2


GLBufferCollection = dict[BufferType, GLBuffer]


class ITransformControllerGLBufferManager(abc.ABC):
    """Interface to a class that returns GL Buffers for transform control points"""

    @abc.abstractmethod
    def __getitem__(self, item: TransformController) -> GLBufferCollection:
        raise NotImplementedError()

    def __contains__(self, item: TransformController) -> bool:
        raise NotImplementedError()

    @abc.abstractmethod
    def get_glbuffer(self, key: TransformController, type: BufferType) -> GLBuffer:
        """Fetch the gl buffer for a transform controller of the requested type"""
        raise NotImplementedError()

    @abc.abstractmethod
    def add(self, transform_controller: TransformController) -> GLBufferCollection:
        """Removes buffers for a transform controller"""
        raise NotImplementedError()

    @abc.abstractmethod
    def remove(self, transform_controller: TransformController):
        """Adds buffers for a transform controller"""
        raise NotImplementedError()

    @abc.abstractmethod
    def add_on_transform_controller_add_remove_event_listener(self, func):
        """Notify when a transform controller is added or removed."""
        raise NotImplementedError()

    @abc.abstractmethod
    def remove_on_transform_controller_add_remove_event_listener(self, func):
        """Stop notifying when a transform controller is added or removed."""
        raise NotImplementedError()


class TransformControllerGLBufferManager(ITransformControllerGLBufferManager):
    """Tracks the current transform that is being editted.
    This manager is a bit complicated because until a context is initialized we cannot initialize the buffers
    """
    # We do not always have a context when a transform controller is added.  If there is no context we store None for
    # the GLBufferCollection and initialize it when the context is created
    _transform_controllers: dict[TransformController, GLBufferCollection | None]

    _OnTransformControllerAddRemoveEventListeners: IEventManager[TransformControllerAddRemoveCallback]
    _buffer_layouts: dict[BufferType, VertexArrayLayout]
    _glcontext_manager: IGLContextManager
    _have_context: bool = False  # True if we've got a context from the context manager

    def __init__(self, glcontext_manager: IGLContextManager, buffer_layouts: dict[BufferType, VertexArrayLayout]):
        self._glcontext_manager = glcontext_manager
        self._OnTransformControllerAddRemoveEventListeners = wxEventManager[TransformControllerAddRemoveCallback]()
        self._transform_controllers = {}
        self._buffer_layouts = buffer_layouts
        self._OnTransformControllerChangeEventListeners = set()
        self._glcontext_manager.add_glcontext_added_event_listener(self._on_gl_context_added)

    def add(self, transform_controller: TransformController) -> GLBufferCollection | None:
        """
        Creates buffers for a transform controller.
        :return: The buffer collection if a GL context is initialized, otherwise None.
        """
        buffer_collection = self._initialize_buffer_collection() if self._have_context else None
        if buffer_collection is not None:
            buffer_collection[BufferType.ControlPoint].data = transform_controller.points

        if transform_controller in self._transform_controllers:
            raise KeyError(f"Transform controller {transform_controller} already exists in the manager")

        print(f'Adding transform controller {transform_controller} with buffer collection {buffer_collection}')

        self._transform_controllers[transform_controller] = buffer_collection
        self._fire_on_transform_controller_add_remove_event(Action.ADD, transform_controller)
        transform_controller.AddOnChangeEventListener(self._on_transform_changed)
        return buffer_collection

    def remove(self, transform_controller: TransformController):
        """Adds buffers for a transform controller"""
        print(f'Removing transform controller {transform_controller}')
        del self._transform_controllers[transform_controller]
        self._fire_on_transform_controller_add_remove_event(Action.REMOVE, transform_controller)

    def _on_gl_context_added(self, context):
        """We only care that there is at least one context, so set our initialized flag and stop subscribing"""
        self._have_context = True
        self._glcontext_manager.remove_glcontext_added_event_listener(self._on_gl_context_added)

        # Initialize the buffers for all transform controllers
        for transform_controller, bufferinfo in self._transform_controllers.items():
            if bufferinfo is None:
                buffer_collection = self._initialize_buffer_collection()
                self._transform_controllers[transform_controller] = buffer_collection
                if buffer_collection is not None:
                    buffer_collection[BufferType.ControlPoint].data = transform_controller.points
                    buffer_collection[BufferType.Selection].data = np.zeros((len(transform_controller.points), 1),
                                                                            dtype=np.uint16)

    def _initialize_buffer_collection(self) -> GLBufferCollection:
        """Initialize the buffer for the transform controller"""
        buffer_collection = {}  # Type: GLBufferCollection
        for buffer_type, layout in self._buffer_layouts.items():
            empty_data = np.empty((0, layout.total_elements), dtype=layout.dtype)
            buffer = GLBuffer(layout=self._buffer_layouts[buffer_type],
                              data=empty_data,
                              usage=gl.GL_DYNAMIC_DRAW)
            buffer_collection[buffer_type] = buffer

        return buffer_collection

    @staticmethod
    def __swap_columns(input: NDArray[np.floating]) -> NDArray[np.floating]:
        """
        OpenGL uses X,Y coordinates.  Everything else in Nornir uses Y,X coordinates in numpy arrays.
        This function swaps the columns in pairs to correctly position points on the screen
        """
        output = input[:, [1, 0, 3, 2]]
        return output

    def _on_transform_changed(self, transform_controller: TransformController):
        """Called when the transform controller changes"""
        buffer_collection = self._transform_controllers[transform_controller]
        if buffer_collection is not None:
            control_point_buffer = buffer_collection[BufferType.ControlPoint]
            num_ctrl_points = len(control_point_buffer.data)
            if num_ctrl_points != len(transform_controller.points):
                selection_point_buffer = buffer_collection[BufferType.Selection]
                selection_point_buffer.data = np.zeros((len(transform_controller.points), 1), dtype=np.uint16)

            points = self.__swap_columns(transform_controller.points)
            buffer_collection[BufferType.ControlPoint].data = points

    def add_on_transform_controller_add_remove_event_listener(self, func: TransformControllerAddRemoveCallback):
        self._OnTransformControllerAddRemoveEventListeners.add(func)

    def remove_on_transform_controller_add_remove_event_listener(self, func: TransformControllerAddRemoveCallback):
        self._OnTransformControllerAddRemoveEventListeners.remove(func)

    def _fire_on_transform_controller_add_remove_event(self, action: Action, transform_controller: TransformController):
        """Send event to subscribers"""
        self._OnTransformControllerAddRemoveEventListeners.invoke(action, transform_controller)

    def __contains__(self, item: TransformController) -> bool:
        return item in self._transform_controllers

    def __getitem__(self, item) -> GLBufferCollection:
        return self._transform_controllers[item]

    def get_glbuffer(self, key: TransformController, type: BufferType) -> GLBuffer:
        """Fetch the gl buffer for a transform controller of the requested type.
        If the buffer has not been initialized and we have a context, initialize it,
        otherwise raise an exception"""
        buffers = self._transform_controllers[key]
        if buffers is None:
            raise ValueError("Buffers not initialized")

        return buffers[type]
