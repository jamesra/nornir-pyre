#!/usr/bin/python

from __future__ import annotations
import sys
import atexit

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QSurfaceFormat

import argparse
import atexit
import logging
import os

from dependency_injector.wiring import inject, Provide
from dependency_injector.providers import Provider

# Set the backend to WXAgg before importing pyplot
import matplotlib

matplotlib.use('WebAgg')

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
from pyre.settings import AppSettings

from pyre.ui.windows.mosaicwindow import MosaicWindow
from pyre.ui.windows.stoswindow import StosWindow


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
    fullpath = os.path.join(os.path.dirname(__file__), path)
    try:
        with open(fullpath, 'r') as file:
            return file.read()
    except FileNotFoundError:
        return "README file not found at " + fullpath


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
    # container_interface.transform_control_point_action_maps = pyre.commands.transfom_control_point_action_maps
    # f = stos_container.transform_control_point_action_maps()
    # result = f[nornir_imageregistration.transforms.TransformType.GRID]

    # stos_container.selected_points = pyre.observable.oset.ObservableSet[int](initial_set=None,
    #                                                                         call_wrapper=wx.CallAfter)

    container_interface.check_dependencies()
    container_interface.wire(modules=[__name__], packages=['pyre'])
    stos_container.check_dependencies()
    stos_container.wire(modules=[__name__], packages=['pyre'])

    stos_transform_controller = container_interface.transform_controller()
    transform_glbuffermanager = container_interface.transform_glbuffermanager()
    transform_glbuffermanager.add(stos_transform_controller)

    atexit.register(SaveSettings, settings_provider=container_interface.settings)

    return container_interface


@atexit.register
def SaveSettings(settings_provider: Provider[AppSettings] = Provide[IContainer.settings].provider):
    settings = settings_provider()
    json = settings.model_dump_json(indent=4)
    output_file = os.path.join(os.path.dirname(__file__), 'settings.json')
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
    format.setDepthBufferSize(24)
    QSurfaceFormat.setDefaultFormat(format)


@inject
def Run(image_manager: IImageManager = Provide[IContainer.image_manager],
        imageviewmodel_manager: IImageViewModelManager = Provide[IContainer.imageviewmodel_manager],
        stos_transform_controller: pyre.state.TransformController = Provide[IContainer.transform_controller]):
    # Build the container first
    container = build_container()

    # Get the required services from the container
    image_manager = container.image_manager()
    imageviewmodel_manager = container.imageviewmodel_manager()

    print("Starting Pyre")

    # StartProfilerCheck()

    nornir_shared.misc.SetupLogging(OutputPath=os.path.join(os.curdir, "PyreLogs"), Level=logging.WARNING)

    pyre.state.currentStosConfig = pyre.state.StosState(transform_controller=stos_transform_controller,
                                                        image_manager=image_manager,
                                                        imageviewmodel_manager=imageviewmodel_manager)
    pyre.state.currentMosaicConfig = pyre.state.MosaicState()

    readmetxt = resource_paths.README()
    print(readmetxt)

    # Run the QT application
    main_qt(window_manager=container.window_manager(), stos_transform_controller=stos_transform_controller)


def main_qt(window_manager: IWindowManager = Provide[IContainer.window_manager],
            stos_transform_controller: pyre.state.TransformController = Provide[IContainer.transform_controller]):
    """Main entry point for the QT version of the application"""
    # Context Sharing must be set before creating QApplication
    DefineDefaultSurface()
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)

    # Create the QT application
    app = QApplication(sys.argv)

    # Create the windows
    # mosaic_window = MosaicWindow(None, 1, "Mosaic Viewer")

    # Create STOS windows for source, target, and composite views
    source_window = StosWindow(None, ViewType.Source, "Fixed Image", ViewType.Source)
    target_window = StosWindow(None, ViewType.Target, "Warped Image", ViewType.Target)
    composite_window = StosWindow(None, ViewType.Composite, "Composite Image", ViewType.Composite)

    window_manager.add(ViewType.Source, source_window)
    window_manager.add(ViewType.Target, target_window)
    window_manager.add(ViewType.Composite, composite_window)

    # Show the windows
    #    mosaic_window.show()
    source_window.show()
    target_window.show()
    composite_window.show()

    # Run the application
    sys.exit(app.exec())


if __name__ == "__main__":
    Run()
