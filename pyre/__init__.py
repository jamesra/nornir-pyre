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
* pyre.interfaces: Interface definitions for dependency injection
"""

__all__ = ['ui', 'viewmodels', 'views', 'Windows', 'state', 'resources', 'common', 'Space']

import numpy as np
from numpy.typing import NDArray

vector3 = NDArray[np.floating]  # A 3 element vector
vector2 = NDArray[np.floating]  # A 2 element vector

import pyre.gl_engine as gl_engine
from pyre.gl_engine.shaders import ColorShader, TextureShader, InitializeShaders 
from pyre.space import Space
from pyre.command_interfaces import ICommand, CommandStatus, CommandResult

Windows = {}
