"""Rules for which transform edits are allowed per display space."""

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


def control_point_translate_allowed(
        transform_type: TransformType,
        space: Space,
        view_type: ViewType | None = None) -> bool:
    """True when control-point translate is the expected edit mode."""
    if transform_type == TransformType.RIGID:
        return False
    if transform_type in (TransformType.GRID, TransformType.MESH, TransformType.RBF):
        return True
    return False


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
