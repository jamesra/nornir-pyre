"""Push transform edits onto the Ctrl+Z command history."""

from __future__ import annotations

import copy
from typing import Any, Callable

import numpy as np
from dependency_injector.wiring import Provide, inject
from numpy.typing import NDArray

from nornir_imageregistration import IRigidTransform, cp
from pyre.interfaces.managers.command_history import ICommandHistory


def save_points_undo(
        history: ICommandHistory,
        set_points: Callable[[NDArray[np.floating]], Any],
        points_before: NDArray[np.floating],
) -> None:
    """Record a SetPoints restore for *points_before* (copied, on its own NumPy/CuPy backend)."""
    xp = cp.get_array_module(points_before)
    history.SaveState(
        set_points,
        xp.asarray(points_before, dtype=xp.float64).copy(),
    )


@inject
def save_points_undo_to_history(
        set_points: Callable[[NDArray[np.floating]], Any],
        points_before: NDArray[np.floating],
        history: ICommandHistory = Provide["history_manager"],
) -> None:
    """save_points_undo onto the app's Ctrl+Z history.

    For callers without an injected history. It must stay at module level: dependency_injector only
    injects functions that exist when the package is wired, so an @inject closure made inside a
    method gets the Provide marker itself (that silently dropped the Spacebar undo, 2026-11-19).
    The provider is named by string because importing pyre.container from here is circular.
    """
    save_points_undo(history, set_points, points_before)


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
