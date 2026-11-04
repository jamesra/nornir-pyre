"""Mesh transforms in Pyre continue past the control-point hull with the nearest hull triangle's affine.

Matches what image warping does (``assemble.write_to_target_roi_coords``) so tiles, cursor
mapping and the warped image agree outside the hull. Grid and other transform types keep
their own extrapolation; registration and builds are unaffected.
"""
from __future__ import annotations

from typing import Any

import nornir_imageregistration
import numpy as np
from nornir_imageregistration import cp
from nornir_imageregistration.transforms import hull_extrapolation
from nornir_imageregistration.transforms.transform_type import TransformType
from numpy.typing import NDArray


def uses_hull_affine(model: Any) -> bool:
    """True when *model* is a mesh whose out-of-hull mapping Pyre fills with hull affine."""
    return (model is not None
            and getattr(model, 'type', None) == TransformType.MESH
            and hull_extrapolation.supports_hull_extrapolation(model))


def map_points(model: Any, points: NDArray[np.floating], *, forward: bool, **kwargs) -> NDArray[np.floating]:
    """``model.Transform`` (*forward*) or ``InverseTransform``, with hull affine outside a mesh's hull.

    For meshes the RBF fallback is never built, so this is safe on the UI thread during a
    drag or before the RBF prewarm finishes. Other models are called unchanged.
    """
    fn = model.Transform if forward else model.InverseTransform
    if not uses_hull_affine(model):
        return fn(points, **kwargs)
    kwargs['extrapolate'] = False
    query = nornir_imageregistration.EnsurePointsAre2DArray(points)
    return _fill_outside_hull(model, query, fn(query, **kwargs), forward=forward)


def _fill_outside_hull(model: Any, query: NDArray[np.floating], mapped: NDArray[np.floating],
                       *, forward: bool) -> NDArray[np.floating]:
    xp = cp.get_array_module(mapped)
    outside = xp.isnan(mapped).any(axis=1)
    outside_host = nornir_imageregistration.EnsureNumpyArray(outside)
    if not outside_host.any():
        return mapped
    extrapolator = (hull_extrapolation.forward_extrapolator(model) if forward
                    else hull_extrapolation.inverse_extrapolator(model))
    rows = nornir_imageregistration.EnsureNumpyArray(query, dtype=np.float64)[outside_host]
    mapped = mapped.copy()
    mapped[outside] = xp.asarray(extrapolator(rows), dtype=mapped.dtype)
    return mapped
