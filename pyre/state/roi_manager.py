"""Tracks selectable objects in a view

A manager contains objects that listen to input events in a specific region.
The manager will notify the objects when an event occurs in their region.
objects report the distance to the input event, and the manager will select the object with the smallest distance.

The manager then walks the responding objects from nearest to furthest and asks if they can start
a new command for the input.  The first object to return a command is selected and the command is executed.
"""

from __future__ import annotations
import abc
import dataclasses

import numpy as np
from numpy.typing import NDArray
import nornir_imageregistration
from nornir_imageregistration import PointLike
import enum

from pyre.commands.interfaces import ICommand
