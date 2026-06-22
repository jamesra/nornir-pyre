"""Interface definitions (and shared types) for managers. Implementations live in pyre.state.managers."""

from .buffertype import BufferType, GLBufferCollection
from .command_history import ICommandHistory
from .gl_context_manager import IGLContextManager
from .image_manager import (IImageLoader, IImageManager, ImageManagerChangeCallback)
from ..named_tuples import ImageLoadResult
from .mouse_position_history_manager import IMousePositionHistoryManager, MousePositionHistoryChangedCallbackEvent
from .region_manager import IRegion, IRegionMap
from .transform_controller_glbuffer_manager import ITransformControllerGLBufferManager
from .window_manager import IWindowManager, WindowManagerChangeCallback
from .image_viewmodel_manager import IImageViewModelManager, ImageViewModelManagerChangeCallback
from .control_point_map_manager import IControlPointMapManager, ControlPointManagerKey
from .command_queue import ICommandQueue
from .command_manager import IControlPointActionMap, IActionMap
