'''
Created on Sep 12, 2013

@author: u0490822
'''

import logging
import os
import numpy
from numpy.typing import NDArray

from OpenGL.GL import *
from OpenGL.GLU import *

from pkg_resources import resource_filename
import nornir_imageregistration


def ResourcePath():
    Logger = logging.getLogger("resources")
    rpath = resource_filename(__name__, "resources")
    # rpath = os.path.join(PackagePath(), 'resources')
    Logger.info('Resources path: ' + rpath)
    return rpath


def README():
    '''Returns README.txt file as a string'''

    readmePath = resource_filename(__name__, "README.txt")

    # readmePath = os.path.join(PackagePath(), "readme.txt")
    if not os.path.exists(readmePath):
        return "No readme.txt was found in " + readmePath

    with open(readmePath, 'r') as hReadme:
        Readme = hReadme.read()
        hReadme.close()
        return Readme
