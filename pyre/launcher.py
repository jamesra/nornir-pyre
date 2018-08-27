'''
Created on Sep 12, 2013

@author: u0490822
'''

import argparse
import logging
import os
import sys

import nornir_shared.misc

from PyreGui import StosWindow
from pyre import Windows
from pyre.state import InitializeStateFromArguments
import resources
 
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


def Run():

    print("Starting Pyre")
 
    StartProfilerCheck()

    nornir_shared.misc.SetupLogging(os.curdir, Level=logging.WARNING)

    readmetxt = resources.README()
    print(readmetxt) 

    args = ProcessArgs()
    arg_values = args.parse_args()

    app = wx.App(False)

    Windows["Fixed"] = StosWindow(None, "Fixed", 'Fixed Image', showFixed=True)
    Windows["Warped"] = StosWindow(None, "Warped", 'Warped Image')
    Windows["Composite"] = StosWindow(None, "Composite", 'Composite', showFixed=True, composite=True)
    # Windows["Mosaic"] = PyreGui.MosaicWindow(None, "Mosaic", 'Mosaic')
 
    InitializeStateFromArguments(arg_values)

    app.MainLoop()

    print("Exiting main loop")

    EndProfilerCheck()


if __name__ == '__main__':
    pass
