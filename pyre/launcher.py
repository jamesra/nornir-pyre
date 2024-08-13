'''
Created on Sep 12, 2013

@author: u0490822
'''

import argparse
import logging
import os

import nornir_shared.misc
import pyre.state.imageloader

from pyre.ui.windows.stoswindow import StosWindow
from pyre import Windows
from pyre.space import Space
import pyre.state
import pyre.gl_engine.shaders as shaders
import pyre.resources
from . import resources
from . import resource_paths
from pyre.state.transformcontroller_glbuffer_manager import BufferType, TransformControllerGLBufferManager, \
    ITransformControllerGLBufferManager
from pyre.state.viewtype import ViewType

import wx

app = None


def ProcessArgs():
    # conflict_handler = 'resolve' replaces old arguments with new if both use the same option flag
    parser = argparse.ArgumentParser('pyre', conflict_handler='resolve')

    parser.add_argument('-Fixed',
                        action='store',
                        required=False,
                        type=str,
                        default=None,
                        help='Path to the fixed image',
                        dest='FixedImageFullPath'
                        )

    parser.add_argument('-Warped',
                        action='store',
                        required=False,
                        type=str,
                        default=None,
                        help='Path to the image to be warped',
                        dest='WarpedImageFullPath'
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


__profiler = None


def StartProfilerCheck():
    if 'PROFILE' in os.environ:
        profile_val = os.environ['PROFILE']
        if len(profile_val) > 0 and profile_val != '0':
            import cProfile
            print("Starting profiler because PROFILE environment variable is defined")
            __profiler = cProfile.Profile()
            __profiler.enable()


def EndProfilerCheck():
    if not __profiler is None:
        __profiler.dump_stats("C:\Temp\pyre.profile")


def OnImageAdded(action, key, value):
    print("Image added: " + key)


def Run():
    print("Starting Pyre")

    StartProfilerCheck()

    nornir_shared.misc.SetupLogging(OutputPath=os.path.join(os.curdir, "PyreLogs"), Level=logging.WARNING)

    gl_context_manager = pyre.state.GLContextManager()

    mouse_position_history_manager = pyre.state.MousePositionHistoryManager()

    # Initialize shaders when a context is created
    gl_context_manager.add_glcontext_added_event_listener(lambda context: shaders.InitializeShaders())
    gl_context_manager.add_glcontext_added_event_listener(
        lambda context: pyre.resources.point_textures.PointTextures.LoadTextures())

    imagetransformview_layouts = {
        BufferType.ControlPoint: shaders.controlpointset_shader.pointset_layout,
        BufferType.Selection: shaders.controlpointset_shader.texture_index_layout
    }

    window_manager = pyre.state.WindowManager()

    image_manager = pyre.state.image_manager.ImageManager()
    imageviewmodel_manager = pyre.state.image_viewmodel_manager.ImageViewModelManager()

    transform_controller = pyre.state.TransformController()
    transform_glbuffermanager = TransformControllerGLBufferManager(glcontext_manager=gl_context_manager,
                                                                   buffer_layouts=imagetransformview_layouts)  # type: ITransformControllerGLBufferManager
    transform_glbuffermanager.add(transform_controller)
    imageviewmodel_manager = pyre.state.image_viewmodel_manager.ImageViewModelManager()

    pyre.state.currentStosConfig = pyre.state.StosState(transform_controller=transform_controller,
                                                        image_manager=image_manager,
                                                        imageviewmodel_manager=imageviewmodel_manager)
    pyre.state.currentMosaicConfig = pyre.state.MosaicState()

    image_loader = pyre.state.imageloader.ImageLoader(transform_controller=transform_controller,
                                                      image_manager=image_manager,
                                                      imageviewmodel_manager=imageviewmodel_manager,
                                                      search_dirs=None)

    stos_window_config = pyre.state.StosWindowConfig(glcontext_manager=gl_context_manager,
                                                     transform_controller=transform_controller,
                                                     transformglbuffer_manager=transform_glbuffermanager,
                                                     imageviewmodel_manager=imageviewmodel_manager,
                                                     window_manager=window_manager,
                                                     image_loader=image_loader,
                                                     mouse_position_history_manager=mouse_position_history_manager)

    readmetxt = resource_paths.README()
    print(readmetxt)

    args = ProcessArgs()
    arg_values = args.parse_args()

    app = wx.App(False)

    window_manager.add(ViewType.Fixed.value,
                       StosWindow(None, ViewType.Source, 'Source Image', view_type=ViewType.Source,
                                  config=stos_window_config))
    window_manager.add(ViewType.Warped.value,
                       StosWindow(None, ViewType.Target, 'Target Image', view_type=ViewType.Target,
                                  config=stos_window_config))
    window_manager.add(ViewType.Composite.value,
                       StosWindow(None, ViewType.Composite, 'Composite Image', view_type=ViewType.Composite,
                                  config=stos_window_config))

    # Windows["Mosaic"] = PyreGui.MosaicWindow(None, "Mosaic", 'Mosaic')

    image_loader = pyre.state.imageloader.ImageLoader(transform_controller,
                                                      image_manager,
                                                      imageviewmodel_manager,
                                                      search_dirs=None)
    pyre.state.InitializeStateFromArguments(image_loader, arg_values)

    # Initialize the GL state

    app.MainLoop()

    print("Exiting main loop")

    EndProfilerCheck()


if __name__ == '__main__':
    pass
