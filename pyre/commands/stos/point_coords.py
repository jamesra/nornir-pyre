"""Shared helpers for building control-point rows from UI mouse positions."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

import nornir_imageregistration
from nornir_imageregistration import cp
from pyre.array_host import yx_host
from pyre.selection_event_data import PointPair
from pyre.space import Space
from pyre.interfaces.viewtype import ViewType


def to_host_scalar(value: object) -> float:
    """Convert a NumPy or CuPy scalar to a Python float for point-row construction."""
    xp = cp.get_array_module(value)
    flat = xp.reshape(xp.asarray(value), (-1,))
    host = nornir_imageregistration.EnsureNumpyArray(flat, dtype=np.float64)
    return float(host[0])


def control_point_row_from_pair(point: PointPair) -> NDArray[np.floating]:
    """Return a (target_y, target_x, source_y, source_x) row for AddPoint."""
    return np.array([
        to_host_scalar(point.target[0]),
        to_host_scalar(point.target[1]),
        to_host_scalar(point.source[0]),
        to_host_scalar(point.source[1]),
    ], dtype=np.float32)


def known_space_for_control_point_create(
        space: Space,
        view_type: ViewType | None,
) -> Space:
    """Return the space of the click used to create a control point.

    Composite panels report ``Space.Source`` but mouse coordinates are
    display/target.
    """
    if view_type == ViewType.Composite:
        return Space.Target
    return space


def known_yx_from_pair(point: PointPair, known_space: Space) -> NDArray[np.floating]:
    """Return the YX click coordinate from a mouse-history pair."""
    value = point.target if known_space == Space.Target else point.source
    return yx_host(value)
