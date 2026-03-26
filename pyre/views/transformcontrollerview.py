from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QOpenGLContext
import numpy as np
from numpy.typing import NDArray
from typing import AbstractSet, Sequence, Iterable, Callable
from dependency_injector.wiring import Provide

from PyQt6.QtOpenGL import QOpenGLFunctions_4_1_Core as QOpenGLFunctions

from nornir_imageregistration import ITransform
import pyre
from pyre.observable import ObservableSet, ObservedAction
from pyre.container import IContainer
from pyre.controllers import TransformController
from pyre.space import Space
from pyre.views.pointview import PointView
import pyre.controllers
from pyre.interfaces.managers.buffertype import BufferType


class BinarySelectionMapper:
    """Maps an observable set of integers to a binary ndarray"""
    _selection: ObservableSet[int]
    _setter: Callable[[NDArray[np.bool_]], None]

    def __init__(self, selection: ObservableSet[int],
                 getter: Callable[[], NDArray[np.bool_]],
                 setter: Callable[[NDArray[np.bool_]], None]):
        self._selection = selection
        self._getter = getter
        self._setter = setter
        self._selection.add_observer(self._OnSelectionChanged)

    def _OnSelectionChanged(self, obj: ObservableSet[int], action: ObservedAction, indicies: AbstractSet[int] | None):
        """Converts the set of integers to a binary array with the integer values set to true"""

        # Determine the length of the array we are writing to.
        length = len(self._getter())
        selected = np.zeros(length, dtype=bool)
        index = TransformController._ensure_numpy_friendly_index(obj)

        if np.any(index >= length):
            raise ValueError("index is out of bounds")

        # Set the values at the indices to true
        selected[index] = True
        self._setter(selected)


class TransformControllerView:
    """Renders the control points of a transform"""
    _transform_controller: pyre.controllers.TransformController | None
    _controlpoint_view: PointView | None
    _transformglbuffer_manager: pyre.interfaces.managers.ITransformControllerGLBufferManager = Provide[  # type: ignore[attr-defined]
        IContainer.transform_glbuffermanager]
    _gl_context_manager: pyre.interfaces.managers.IGLContextManager = Provide[IContainer.glcontext_manager]  # type: ignore[attr-defined]

    _initialized: bool = False

    _gl_funcs: QOpenGLFunctions | None = None

    @property
    def gl_funcs(self) -> QOpenGLFunctions:
        """The OpenGL functions used to create the frame buffer"""
        if self._gl_funcs is None:
            self._gl_funcs = QOpenGLFunctions()
            self._gl_funcs.initializeOpenGLFunctions()
        return self._gl_funcs

    def __init__(self,
                 transform_controller: pyre.controllers.TransformController | None,
                 gl_funcs: QOpenGLFunctions | None = None,
                 ):
        """
        :param transform_controller:
        :param selected_points: A set indicating which points are selected.  If None, no points are selectable.
        selected points at index 1
        """
        self._gl_funcs = gl_funcs
        self._controlpoint_view = None
        self._transform_controller = transform_controller
        self._transform_controller.AddOnChangeEventListener(self._OnTransformChange)  # type: ignore[union-attr]
        self._transform_controller.AddOnModelReplacedEventListener(self._OnTransformModelReplaced)  # type: ignore[union-attr]
        self._initialized = False
        self._gl_context_manager.add_glcontext_added_event_listener(self.create_objects)
        # pyre.state.currentStosConfig.AddOnTransformControllerChangeEventListener(self._OnTransformControllerChange)

    def create_objects(self, context: QOpenGLContext):
        """"Creates opengl objects when opengl is initialized
        
        Args:
            context: The OpenGL context that was just created. This should already be current
                    when this method is called thanks to GLContextManager ensuring context activation.
        """
        if self._initialized:
            return True

        # Validate the provided context (it should already be current)
        if not context or not context.isValid():
            raise RuntimeError("OpenGL context is not valid")

        # Verify context is current (should be guaranteed by GLContextManager)
        current = QOpenGLContext.currentContext()
        if current != context:
            print(f"Warning: Expected context {context} but current is {current}")

        # Check if buffers are initialized - they may not be ready yet if context was just created
        if self._transform_controller is None:
            print("Warning: Transform controller is None, cannot create objects")
            return False
            
        # Check if buffers are initialized
        if self._transform_controller not in self._transformglbuffer_manager:
            print(f"Warning: Transform controller {self._transform_controller} not in buffer manager yet")
            return False

        buffers = self._transformglbuffer_manager[self._transform_controller]
        if buffers is None:
            print(f"Warning: Buffers not initialized for transform controller {self._transform_controller}, deferring object creation")
            return False

        self._initialized = True
        self._gl_context_manager.remove_glcontext_added_event_listener(self.create_objects)

        glcontrolpointbuffer = self._transformglbuffer_manager.get_glbuffer(
            self._transform_controller,
            BufferType.ControlPoint)
        glselectionbuffer = self._transformglbuffer_manager.get_glbuffer(
            self._transform_controller,
            BufferType.Selection)
        self._controlpoint_view = PointView(points=glcontrolpointbuffer,
                                            texture_indicies=glselectionbuffer,
                                            texture_array=pyre.resources.pointtextures.PointArray,
                                            gl_funcs=self.gl_funcs)
        # Sync current controller points into the shared buffer (handles transform loaded after context creation)
        self._controlpoint_view.points = self._transform_controller.points
        # Deferred sync so we pick up points if transform is set in same tick after context creation
        QTimer.singleShot(0, self._sync_control_points_from_controller)


    def _sync_control_points_from_controller(self):
        """Sync controller points into the control point view buffer (safe to call deferred)."""
        if self._controlpoint_view is not None and self._transform_controller is not None:
            self._controlpoint_view.points = self._transform_controller.points

    def _OnTransformControllerChange(self, new_transform_controller: pyre.controllers.TransformController | None):
        if self._transform_controller is not None:
            self._transform_controller.RemoveOnChangeEventListener(self._OnTransformChange)

        self._transform_controller = new_transform_controller

        if self._transform_controller is not None:
            self._transform_controller.AddOnChangeEventListener(self._OnTransformChange)

    def _OnTransformChange(self, *args, **kwargs):
        if self._controlpoint_view is None:
            return

        tc_points = self._transform_controller.points  # type: ignore[union-attr]
        tc_points = tc_points.get() if hasattr(tc_points, "get") else tc_points  # type: ignore[attr-defined]
        buf_points = self._controlpoint_view.points
        # Skip allclose when lengths differ (avoids shape-mismatch; buffer may be stale empty)
        if buf_points.shape[0] == tc_points.shape[0] and np.allclose(buf_points, tc_points):
            return

        reset_selection = len(self._controlpoint_view.texture_index) != self._controlpoint_view.points.shape[0]

        self._controlpoint_view.points = self._transform_controller.points  # type: ignore[union-attr]

        if reset_selection:
            self.selected = None

    def _OnTransformModelReplaced(self, controller: TransformController, old: ITransform, new: ITransform):
        """The transform model object has changed.  Reset everything"""
        if self._controlpoint_view is None:
            return

        self._controlpoint_view.points = self._transform_controller.points  # type: ignore[union-attr]
        self.selected = None

    @property
    def selected(self) -> NDArray[np.bool_]:
        return self._controlpoint_view.texture_index.astype(bool)  # type: ignore[union-attr]

    @selected.setter
    def selected(self, value: NDArray[np.bool_] | NDArray[np.integer] | None):
        """
        Set the selected control points
        :param value: Passing None will deselect all points, otherwise a boolean or integer array representing the texture index that should be used for points
        :return:
        """
        if value is None:
            self._controlpoint_view.texture_index = np.zeros(self._controlpoint_view.points.shape[0], dtype=np.uint16)  # type: ignore[union-attr, assignment]
            return

        if value.shape[0] != self._controlpoint_view.points.shape[0]:  # type: ignore[union-attr]
            raise ValueError("Selected array must have the same number of elements as the control points")

        if value.dtype == np.integer:
            if max(value) >= self._controlpoint_view.num_textures:  # type: ignore[union-attr]
                raise ValueError(
                    "Selected array of integer values contains indices larger than the number of textures in texture array")
            if min(value) < 0:
                raise ValueError("Selected array of integer values contains indices that are negative")

        self._controlpoint_view.texture_index = value.astype(np.uint16)  # type: ignore[union-attr, assignment]

    def set_selected_by_index(self, index: Iterable[int] | NDArray[np.integer]):
        """Converts passed sequences of integers into a boolean array where values at the index are true"""
        selected = np.zeros(self._controlpoint_view.points.shape[0], dtype=bool)  # type: ignore[union-attr]
        np_index = TransformController._ensure_numpy_friendly_index(index)  # type: ignore[arg-type]

        if np.any(np_index >= self._controlpoint_view.points.shape[0]):  # type: ignore[union-attr]
            raise ValueError("Selected index is out of bounds")

        selected[np_index] = True  # type: ignore[index]
        self.selected = selected

    def draw(self, model_view_proj_matrix: NDArray[np.floating], tween: float, scale_factor: float):
        if self._controlpoint_view is None:
            return

        # Sync points when GL context is current (deferred sync may have run without context)
        n_controller = len(self._transform_controller.points)  # type: ignore[union-attr]
        n_buffer = len(self._controlpoint_view.points)
        if n_buffer != n_controller:
            self._controlpoint_view.points = self._transform_controller.points  # type: ignore[union-attr]

        self._controlpoint_view.draw(model_view_proj_matrix, tween, scale_factor)

