"""Push transform edits onto the Ctrl+Z command history."""

from __future__ import annotations

import copy
from typing import Any, Callable

import numpy as np
from numpy.typing import NDArray

from nornir_imageregistration import IRigidTransform
from pyre.interfaces.managers.command_history import ICommandHistory


def save_points_undo(
        history: ICommandHistory,
        set_points: Callable[[NDArray[np.floating]], Any],
        points_before: NDArray[np.floating],
) -> None:
    """Record a SetPoints restore for *points_before* (copied)."""
    history.SaveState(
        set_points,
        np.asarray(points_before, dtype=np.float64).copy(),
    )


def restore_rigid_state(controller: object, state: dict[str, Any]) -> None:
    """Restore a GetRigidState snapshot onto the live TransformModel in place."""
    model = getattr(controller, "TransformModel", None)
    if isinstance(model, IRigidTransform):
        model.SetRigidState(state)


def rigid_state_changed(
        before: dict[str, Any],
        after: dict[str, Any],
) -> bool:
    """True when two rigid-parameter snapshots differ."""
    if before.keys() != after.keys():
        return True
    for key, value in before.items():
        other = after[key]
        if isinstance(value, np.ndarray) or isinstance(other, np.ndarray):
            if not np.allclose(value, other, rtol=1e-5, atol=1e-3):
                return True
        elif value != other:
            return True
    return False


def save_rigid_undo(
        history: ICommandHistory,
        controller: object,
        state_before: dict[str, Any],
) -> None:
    """Record an in-place rigid restore for *state_before* (deep-copied)."""
    history.SaveState(
        restore_rigid_state,
        controller,
        copy.deepcopy(state_before),
    )
