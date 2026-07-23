"""Rules for which transform edits are allowed per display space."""

from typing import Any

from nornir_imageregistration.transforms.base import IControlPointEdit, ITargetSpaceControlPointEdit
from nornir_imageregistration.transforms.transform_type import TransformType

from pyre.interfaces.action import ControlPointAction
from pyre.interfaces.viewtype import ViewType
from pyre.space import Space


def fixed_image_manipulation_locked(
        transform_type: TransformType,
        space: Space,
        view_type: ViewType | None = None) -> bool:
    """True when the standalone fixed-image panel must not translate or rotate the layer."""
    if view_type == ViewType.Composite:
        return False
    return space == Space.Source and transform_type in (TransformType.RIGID, TransformType.GRID)


def rigid_rotation_locked(
        transform_type: TransformType,
        view_type: ViewType | None = None) -> bool:
    """True when Ctrl+scroll rotation must not run (rigid: Composite window only)."""
    if transform_type != TransformType.RIGID:
        return False
    return view_type != ViewType.Composite


def wheel_rotate_locked(
        transform_type: TransformType,
        space: Space,
        view_type: ViewType | None = None) -> bool:
    """True when Ctrl+scroll layer rotation must not run for this panel."""
    if fixed_image_manipulation_locked(transform_type, space, view_type):
        return True
    return rigid_rotation_locked(transform_type, view_type)


def layer_translate_locked(
        transform_type: TransformType,
        space: Space,
        view_type: ViewType | None = None) -> bool:
    """True when empty-space drag must not translate the whole layer."""
    return fixed_image_manipulation_locked(transform_type, space, view_type)


def fixed_panel_control_points_locked(
        transform_model: Any,
        space: Space,
        view_type: ViewType | None = None) -> bool:
    """True when fixed-panel control points are view-only (target-space-only transforms)."""
    if view_type == ViewType.Composite or space != Space.Source:
        return False
    return (
        isinstance(transform_model, ITargetSpaceControlPointEdit)
        and not isinstance(transform_model, IControlPointEdit)
    )


def fixed_panel_hint_message(
        transform_model: Any,
        transform_type: TransformType,
        space: Space,
        view_type: ViewType | None = None) -> str | None:
    """Corner-hint text for the standalone fixed panel, or None when no hint applies."""
    if view_type == ViewType.Composite or space != Space.Source:
        return None
    if fixed_panel_control_points_locked(transform_model, space, view_type):
        return (
            "Grid transform — fixed control points cannot be moved here; "
            "adjust warped points in the Warped view")
    if fixed_image_manipulation_locked(transform_type, space, view_type):
        if transform_type == TransformType.RIGID:
            return (
                "Fixed image — translate warped layer in Warped or Composite; "
                "rotate in Composite view")
        return "Fixed image — translate warped layer in Warped or Composite view"
    return None


def blocks_control_point_translate_action(
        transform_model: Any,
        space: Space,
        action: ControlPointAction,
        view_type: ViewType | None = None) -> bool:
    """True when a control-point drag must be ignored in this panel."""
    if action != ControlPointAction.TRANSLATE:
        return False
    return fixed_panel_control_points_locked(transform_model, space, view_type)


def blocks_layer_translate_action(
        transform_type: TransformType,
        space: Space,
        action: ControlPointAction,
        view_type: ViewType | None = None) -> bool:
    """True when a whole-layer translate action must be ignored on the fixed panel."""
    if not layer_translate_locked(transform_type, space, view_type):
        return False
    if action == ControlPointAction.TRANSLATE_ALL:
        return True
    return action == ControlPointAction.TRANSLATE and transform_type == TransformType.RIGID
