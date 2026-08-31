"""
Pyre - Python Registration Environment

A Python-based image registration and visualization tool for scientific image processing,
developed as part of the Nornir project.

Pyre provides an interactive interface for:
* Manual and automatic image alignment
* Visualization of image transformations
* Creation and editing of spatial transformations between images
* Management of image mosaics and volumes
* Integration with the broader Nornir image processing ecosystem

For complete documentation including keyboard and mouse controls,
please refer to the main README.rst file in the repository root.

Project Structure:
-----------------
* pyre.gl_engine: OpenGL rendering engine for high-performance image visualization
* pyre.ui: User interface components built with PyQt6
* pyre.views: View implementations for different visualization modes
* pyre.state: State management and controllers
* pyre.commands: Command pattern implementations for operations
* pyre.interfaces: Interface definitions (commands, view types, managers, etc.) for dependency injection
* pyre.space: Space enum (source/target) at package root for historical use; also re-exported via pyre.Space
"""

__all__ = ['ui', 'viewmodels', 'views', 'state', 'resources', 'common', 'Space']

import pydantic
import numpy as np
from numpy.typing import NDArray


def _enable_pydantic_v2_basesettings_compat() -> None:
    """Avoid Pydantic v2 BaseSettings migration errors from hasattr() probes.

    Some dependencies still test `hasattr(pydantic, "BaseSettings")`.
    Pydantic v2 raises PydanticImportError for that attribute, which can
    bubble out of C-level PyObject_HasAttr calls. We convert that one legacy
    lookup into a normal missing-attribute response.
    """

    old_getattr = getattr(pydantic, "__getattr__", None)
    if old_getattr is None or getattr(pydantic, "_pyre_bs_compat", False):
        return

    def _compat_getattr(name: str):
        if name == "BaseSettings":
            raise AttributeError(name)
        return old_getattr(name)

    pydantic.__getattr__ = _compat_getattr  # type: ignore[assignment]
    pydantic._pyre_bs_compat = True  # type: ignore[attr-defined]


_enable_pydantic_v2_basesettings_compat()

vector3 = NDArray[np.floating]  # A 3 element vector
vector2 = NDArray[np.floating]  # A 2 element vector

import pyre.gl_engine as gl_engine
from pyre.gl_engine.shaders import ColorShader, TextureShader, InitializeShaders
from pyre.space import Space
from pyre.interfaces import ICommand, CommandStatus, CommandResult

import pyre.ui as ui
import pyre.viewmodels as viewmodels
import pyre.views as views
import pyre.state as state
import pyre.resources as resources
import pyre.common as common
