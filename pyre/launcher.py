#!/usr/bin/python
"""
Launcher module for the Pyre application.

This module serves as the main entry point for the Pyre application. It handles:
1. Command-line argument processing
2. Dependency injection container setup
3. Application initialization
4. Window creation and management
5. OpenGL context configuration

The module provides two main entry points:
- Run(): Legacy entry point for the application
- main_qt(): Modern entry point using the QT interface

Usage:
    To start Pyre with no arguments (empty workspace is valid)::

        pyre
        python -m pyre

    Optional command-line arguments:

    -Fixed: Path to the target (fixed) image
    -Warped: Path to the image to be warped (source)
    -stos: Path to a STOS file to load
    -mosaic: Path to a mosaic file to load
    -tiles: Path to the tiles referred to in the mosaic file
"""

from __future__ import annotations
import sys
import atexit
import io

from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QSurfaceFormat

import argparse
import logging
import os

from dependency_injector.wiring import inject, Provide
from dependency_injector.providers import Provider

import matplotlib
import nornir_imageregistration

# Use Qt backend for matplotlib (compatible with PyQt6)
matplotlib.use('QtAgg')

import nornir_shared.misc
from pyre.interfaces.managers import IImageViewModelManager, IWindowManager
from pyre.interfaces.managers.image_manager import IImageManager
import pyre.ui
import pyre.gl_engine.shaders as shaders 
import pyre.resources
from pyre.interfaces.viewtype import ViewType
from . import resource_paths

from pyre.container import IContainer
from pyre.stos_container import StosContainer
import pyre.commands.stos
from pyre.frozen_paths import configure_frozen_environment, is_frozen, user_settings_path
from pyre.settings import AppSettings
from pyre.ui.window_geometry import apply_saved_window_geometry, capture_window_geometry

from pyre.ui.windows.mosaicwindow import MosaicWindow
from pyre.ui.windows.stoswindow import StosWindow


class TeeOutput:
    """A class that writes to both console and a file"""

    def __init__(self, file_path: str, original_stream):
        self.file = open(file_path, 'w', encoding='utf-8', buffering=1)  # Line buffered
        self.original_stream = original_stream

    def write(self, text: str):
        if self.original_stream is not None:
            self.original_stream.write(text)
        self.file.write(text)
        self.file.flush()  # Ensure it's written immediately

    def flush(self):
        if self.original_stream is not None:
            self.original_stream.flush()
        self.file.flush()

    def close(self):
        if self.file:
            self.file.close()


class TeeStderr:
    """A class that writes stderr to both console and a file"""

    def __init__(self, file_path: str, original_stderr, shared_file=None):
        # Use shared file if provided (from stdout), otherwise open our own
        if shared_file:
            self.file = shared_file
            self.own_file = False
        else:
            self.file = open(file_path, 'a', encoding='utf-8', buffering=1)  # Append mode
            self.own_file = True
        self.original_stderr = original_stderr

    def write(self, text: str):
        if self.original_stderr is not None:
            self.original_stderr.write(text)
        self.file.write(text)
        self.file.flush()  # Ensure it's written immediately

    def flush(self):
        if self.original_stderr is not None:
            self.original_stderr.flush()
        self.file.flush()

    def close(self):
        # Only close if we own the file (not if it's shared with stdout)
        if self.own_file and self.file:
            self.file.close()


_console_log_file = None
_console_stderr_file = None
_original_stdout = None
_original_stderr = None
_original_excepthook = None


def _exception_handler(exc_type, exc_value, exc_traceback):
    """Custom exception handler that ensures exceptions are logged to file"""
    global _console_log_file, _original_excepthook

    # Write exception to log file if available
    if _console_log_file and _console_log_file.file:
        import traceback
        try:
            _console_log_file.file.write("\n" + "=" * 80 + "\n")
            _console_log_file.file.write("UNHANDLED EXCEPTION:\n")
            _console_log_file.file.write("=" * 80 + "\n")
            traceback.print_exception(exc_type, exc_value, exc_traceback, file=_console_log_file.file)
            _console_log_file.file.write("=" * 80 + "\n")
            _console_log_file.file.flush()  # Ensure it's written immediately
        except Exception:
            pass  # Don't fail if we can't write to the log

    # Call original exception handler
    if _original_excepthook:
        _original_excepthook(exc_type, exc_value, exc_traceback)
    else:
        # Fallback to default behavior
        sys.__excepthook__(exc_type, exc_value, exc_traceback)


def _setup_console_logging():
    """Setup console logging to duplicate all output to a log file"""
    global _console_log_file, _console_stderr_file, _original_stdout, _original_stderr, _original_excepthook

    # Save original streams and exception handler
    _original_stdout = sys.stdout
    _original_stderr = sys.stderr
    _original_excepthook = sys.excepthook

    log_file_path = nornir_shared.misc.GetUnifiedConsoleLogPath()
    if log_file_path is None:
        # Fall back to the current working directory when no shared root is configured.
        log_file_path = os.path.join(os.getcwd(), 'pyre-console.log')
    else:
        os.makedirs(os.path.dirname(log_file_path), exist_ok=True)

    # Create tee output that writes to both console and file
    # Share the same file handle between stdout and stderr
    _console_log_file = TeeOutput(log_file_path, _original_stdout)
    _console_stderr_file = TeeStderr(log_file_path, _original_stderr, shared_file=_console_log_file.file)
    sys.stdout = _console_log_file
    sys.stderr = _console_stderr_file

    # Install custom exception handler to capture unhandled exceptions
    sys.excepthook = _exception_handler

    # Register cleanup on exit
    def cleanup():
        global _console_log_file, _console_stderr_file, _original_stdout, _original_stderr, _original_excepthook
        # Flush before closing
        if _console_log_file:
            _console_log_file.flush()
        if _console_stderr_file:
            _console_stderr_file.flush()
        # Restore original streams
        if _console_log_file:
            _console_log_file.close()
            sys.stdout = _original_stdout
        if _console_stderr_file:
            _console_stderr_file.close()
            sys.stderr = _original_stderr
        # Restore original exception handler
        if _original_excepthook:
            sys.excepthook = _original_excepthook

    atexit.register(cleanup)

    # Write initial message using original stdout to avoid recursion
    if _original_stdout is not None:
        _original_stdout.write(f"Console output being logged to: {log_file_path}\n")
    _console_log_file.file.write(f"Console output being logged to: {log_file_path}\n")
    _console_log_file.file.flush()


def ProcessArgs():
    # conflict_handler = 'resolve' replaces old arguments with new if both use the same option flag
    parser = argparse.ArgumentParser('pyre', conflict_handler='resolve')

    parser.add_argument('-Fixed',
                        action='store',
                        required=False,
                        type=str,
                        default=None,
                        help='Path to the target image',
                        dest='TargetImageFullPath'
                        )

    parser.add_argument('-Warped',
                        action='store',
                        required=False,
                        type=str,
                        default=None,
                        help='Path to the image to be warped',
                        dest='SourceImageFullPath'
                        )

    parser.add_argument('-stos',
                        action='store',
                        required=False,
                        type=str,
                        default=None,
                        help='Path to the stos file to load',
                        dest='stosFullPath'
                        )

    parser.add_argument('-mosaic',
                        action='store',
                        required=False,
                        type=str,
                        default=None,
                        help='Path to the mosaic file to load',
                        dest='mosaicFullPath'
                        )

    parser.add_argument('-tiles',
                        action='store',
                        required=False,
                        type=str,
                        default=None,
                        help='Path to the tiles referred to in the mosaic file',
                        dest='mosaicTilesFullPath'
                        )

    return parser


def readme(path) -> str:
    """Load bundled help text; matches resource_paths (prefers repo README.rst)."""
    import pyre.resource_paths as resource_paths
    return resource_paths.readme_text_with_fallback(path)


def build_container() -> IContainer:
    module_dir = os.path.dirname(__file__)
    container_interface = IContainer()

    settings = container_interface.settings()  # type: AppSettings

    stos_container = StosContainer()
    readme_path = settings.readme
    stos_container.config.readme.from_value(readme(readme_path))
    stos_container.init_resources()
    container_interface.override(stos_container)
    container_interface.action_command_map.override(stos_container.action_command_map)

    # Ensure we intialize the shaders and textures before anyone can subscribe to context creation events
    glcontext_manager = stos_container.glcontext_manager()
    glcontext_manager.add_glcontext_added_event_listener(lambda context: shaders.InitializeShaders()) 
    glcontext_manager.add_glcontext_added_event_listener(
        lambda context: pyre.resources.point_textures.PointTextures.LoadTextures())

    # Set the default commands for stos files
    # container_interface.action_command_map = pyre.commands.action_command_map
    # container_interface.transform_control_point_action_maps.override(pyre.commands.transform_control_point_action_maps)
    # container_interface.transform_control_point_action_maps = pyre.commands.transform_control_point_action_maps
    # f = stos_container.transform_control_point_action_maps()
    # result = f[nornir_imageregistration.transforms.TransformType.GRID]

    # Note: ObservableSet no longer needs a call_wrapper with Qt's signal/slot mechanism

    container_interface.check_dependencies()
    container_interface.wire(modules=[__name__], packages=['pyre'])
    stos_container.check_dependencies()
    stos_container.wire(modules=[__name__], packages=['pyre'])

    stos_transform_controller = container_interface.transform_controller()
    transform_gl_buffer_manager = container_interface.transform_gl_buffer_manager()
    transform_gl_buffer_manager.add(stos_transform_controller)

    atexit.register(SaveSettings, settings_provider=container_interface.settings)

    return container_interface


def _settings_output_path() -> str:
    if is_frozen():
        settings_path = user_settings_path()
        os.makedirs(os.path.dirname(settings_path), exist_ok=True)
        return settings_path
    return os.path.join(os.path.dirname(__file__), 'settings.json')


@atexit.register
def SaveSettings(settings_provider: Provider[AppSettings] = Provide[IContainer.settings].provider):
    settings = settings_provider()
    json = settings.model_dump_json(indent=4)
    output_file = _settings_output_path()
    with open(output_file, 'w') as file:
        file.write(json)

    print(f"Saved settings to {output_file}")


def DefineDefaultSurface():
    """Define the default surface format for OpenGL"""
    format = QSurfaceFormat()
    format.setRenderableType(QSurfaceFormat.RenderableType.OpenGL)
    format.setVersion(4, 1)
    format.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
    format.setSwapBehavior(QSurfaceFormat.SwapBehavior.DoubleBuffer)
    format.setDepthBufferSize(16)
    if nornir_imageregistration.in_debug_mode():
        format.setOption(QSurfaceFormat.FormatOption.DebugContext)  # Enable debug output

    QSurfaceFormat.setDefaultFormat(format)


@inject
def Run(image_manager: IImageManager = Provide[IContainer.image_manager],
        image_viewmodel_manager: IImageViewModelManager = Provide[IContainer.image_viewmodel_manager]):
    configure_frozen_environment()

    # Build the container first (before setting up logging to avoid pickling issues)
    container = build_container()

    # Setup console logging to duplicate all output to a log file
    # Done after container build to avoid dependency injection pickling issues
    _setup_console_logging()

    # Resolve services from the wired container (not @inject defaults — wiring happens in build_container).
    image_manager = container.image_manager()
    image_viewmodel_manager = container.image_viewmodel_manager()
    stos_transform_controller = container.transform_controller()

    print("Starting Pyre")

    # StartProfilerCheck()

    nornir_shared.misc.SetupLogging(Level=logging.WARNING)

    pyre.state.set_current_stos_config(pyre.state.StosState(
        transform_controller=stos_transform_controller,
        image_manager=image_manager,
        image_viewmodel_manager=image_viewmodel_manager,
        image_loader=container.image_loader(),
        window_manager=container.window_manager(),
    ))
    pyre.state.set_current_mosaic_config(pyre.state.MosaicState())

    # Run the QT application
    main_qt(window_manager=container.window_manager(), stos_transform_controller=stos_transform_controller)


def main_qt(window_manager: IWindowManager = Provide[IContainer.window_manager],
            stos_transform_controller: pyre.state.TransformController = Provide[IContainer.transform_controller],
            settings: AppSettings = Provide[IContainer.settings]):
    """Main entry point for the QT version of the application"""
    # Context Sharing must be set before creating QApplication
    args = ProcessArgs()
    arg_values = args.parse_args()

    DefineDefaultSurface()
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)

    # Create the QT application (or get existing instance)
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    else:
        print("Warning: QApplication instance already exists, reusing it")

    from pyre.qt_eventmanager import init_main_thread_dispatcher
    init_main_thread_dispatcher()

    # Create the windows
    # mosaic_window = MosaicWindow(None, 1, "Mosaic Viewer")

    # Create STOS windows for source, target, and composite views
    source_window = StosWindow(None, ViewType.Source, "Fixed Image", ViewType.Source)
    target_window = StosWindow(None, ViewType.Target, "Warped Image", ViewType.Target)
    composite_window = StosWindow(None, ViewType.Composite, "Composite Image", ViewType.Composite)

    window_manager.add(ViewType.Source, source_window)
    window_manager.add(ViewType.Target, target_window)
    window_manager.add(ViewType.Composite, composite_window)

    geometry_restored = apply_saved_window_geometry(settings, window_manager)
    if geometry_restored:
        StosWindow.sync_window_visibility_menus(window_manager)

    for view_type in (ViewType.Source, ViewType.Target, ViewType.Composite):
        if view_type in window_manager:
            window_manager[view_type].show()
            window_manager[view_type].raise_()

    def _persist_window_geometry() -> None:
        capture_window_geometry(settings, window_manager)

    app.aboutToQuit.connect(_persist_window_geometry)

    def process_arguments():
        pyre.state.UpdateSettingsFromArguments(arg_values)
        try:
            pyre.state.InitializeStateFromSettings(stos_transform_controller)
        except FileNotFoundError as e:
            QMessageBox.warning(
                None,
                "File Not Found",
                f"The saved STOS file could not be found (the drive may be unmounted):\n\n{e}"
                f"\n\nPyre will start with an empty workspace.",
            )
        except ValueError as e:
            QMessageBox.warning(
                None,
                "Could Not Load STOS File",
                f"The saved STOS file could not be parsed:\n\n{e}"
                f"\n\nPyre will start with an empty workspace.",
            )
        except KeyError as e:
            QMessageBox.warning(
                None,
                "Startup",
                f"Could not restore the previous session:\n\n{e}"
                f"\n\nPyre will start with an empty workspace.",
            )
        if ViewType.Composite in window_manager:
            from pyre.ui.windows.stosfilebrowser import StosFileBrowserWindow
            StosWindow.open_folder_browser_if_cached_folder_exists(
                settings,
                window_manager[ViewType.Composite],
                geometry_restored=geometry_restored,
            )
            if not geometry_restored:
                from PyQt6.QtGui import QGuiApplication
                display_count = len(QGuiApplication.screens())
                if display_count == 1:
                    if not StosFileBrowserWindow.has_cached_folder(settings):
                        StosWindow.apply_single_monitor_composite_layout(window_manager)
                else:
                    for view_type in (ViewType.Source, ViewType.Target, ViewType.Composite):
                        window_manager[view_type].setPosition()
        # Force repaint so control-point draw-time sync runs with loaded transform
        for view_type in (ViewType.Source, ViewType.Target, ViewType.Composite):
            if view_type in window_manager:
                window_manager[view_type].update()

    # Schedule the initialization to occur after the event loop starts
    QTimer.singleShot(0, process_arguments)

    # Run the application
    exit_code = app.exec()
    sys.exit(exit_code)


if __name__ == "__main__":
    Run()
