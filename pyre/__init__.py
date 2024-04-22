'''

Pyre commands
=============

The blinking point is the currently selected point

Mouse
______

Left Button

   ``<Left Click>`` to select an existing point
   
   ``Shift + <Left Click>`` to add a new point
   
   ``Alt+Shift + <Left Click>`` to add a new point and auto-align
   
   ``<Left Click> + drag`` to move point under the cursor
   
   ``Ctrl + <Left Click> + drag`` to translate entire warped image
   
   ``Alt + <Left Click>`` to move currently selected point to mouse position

Right Button

   ``Shift + <Right Click>`` to delete point under the cursor
   
   ``<Right Click> + drag`` to move the view

Scroll wheel

   ``<Scroll wheel>`` zoom in or out
   
   ``Ctrl + <Scroll wheel>`` to rotate warped image
   
   ``Ctrl + Shift + <Scroll wheel>`` to rotate warped image slowly

Keys
____

   ``A,W,S,D`` Move the view
   
   ``Page Up/Down`` Change the magnification

   ``M`` Match the view on all windows to look at the same point as the current window (Not Functional for Warped Image)
   
   ``L`` Show transform mesh lines
   
   ``f`` Flip the warped image
   
   ``Space`` Auto-align the selected point
   
   ``Shift + Space`` Auto-align all points

   ``Ctrl+Z`` to undo a step
   
   ``Ctrl+X`` to redo a step

   ``Tab`` Change properties of the view.  A warped image may be displayed as it appears registered.  The composite view will switch to a different view.

'''

__all__ = ['ui', 'viewmodels', 'views', 'Windows', 'state', 'resources', 'common']

Windows = {}

import pyre.common as common
import pyre.commandhistory
from pyre.commandhistory import history
import pyre.ui as ui
import pyre.viewmodels as viewmodels
import pyre.views as views
from pyre import resources, state
from pyre.shaders import TextureShader

import numpy as np
from numpy.typing import NDArray

vector3 = NDArray[np.floating]  # A 3 element vector
vector2 = NDArray[np.floating]  # A 2 element vector


def Exit():
    '''Destroy all windows and exit the application'''
    for w in list(Windows.values()):
        w.Destroy()


def AnyVisibleWindows():
    AnyVisibleWindows = False
    for w in list(Windows.values()):
        AnyVisibleWindows = AnyVisibleWindows or w.IsShown()

    return AnyVisibleWindows


def ToggleWindow(key):
    if key in Windows:
        w = Windows[key]
        if w.IsShown():
            w.Hide()
        else:
            w.Show()

    if not AnyVisibleWindows():
        Exit()
