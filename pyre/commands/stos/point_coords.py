"""Shared helpers for building control-point rows from UI mouse positions."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

import nornir_imageregistration
from pyre.selection_event_data import PointPair


def to_host_scalar(value: object) -> float:
    """Convert a NumPy or CuPy scalar to a Python float for point-row construction."""
    if nornir_imageregistration.HasCupy():
        try:
            import cupy as cp
            if isinstance(value, cp.ndarray):
                return float(value.item())
        except Exception:
            pass
    return float(value)  # type: ignore[arg-type]


def control_point_row_from_pair(point: PointPair) -> NDArray[np.floating]:
    """Return a (target_y, target_x, source_y, source_x) row for AddPoint."""
    return np.array([
        to_host_scalar(point.target[0]),
        to_host_scalar(point.target[1]),
        to_host_scalar(point.source[0]),
        to_host_scalar(point.source[1]),
    ], dtype=np.float32)
