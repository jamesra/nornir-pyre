"""Host (y, x) vectors for Qt and Python endpoints (not a general NumPy converter)."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

import nornir_imageregistration
from nornir_imageregistration import cp


def yx_host(mapped: object) -> NDArray[np.floating]:
    """Return a host (y, x) vector from a transform mapping or control-point row.

    Uses ``xp.squeeze`` on the input backend, then ``EnsureNumpyArray`` for the
    two-float Qt/Python boundary (create-point, registration snapshot, mouse).
    """
    xp = cp.get_array_module(mapped)
    squeezed = xp.squeeze(xp.asarray(mapped))
    arr = nornir_imageregistration.EnsureNumpyArray(squeezed, dtype=np.float64)
    return np.asarray(arr, dtype=np.float64).ravel()[:2]


def leading_axis_len(arr: object | None) -> int:
    """Return ``arr.shape[0]`` without converting CuPy to NumPy.

    Qt logging and similar host-side counts must not call ``np.asarray`` on
    live transform point arrays.
    """
    if arr is None:
        return 0
    shape = getattr(arr, "shape", None)
    if shape is not None and len(shape) > 0:
        return int(shape[0])
    try:
        return int(len(arr))  # type: ignore[arg-type]
    except TypeError:
        return 0
