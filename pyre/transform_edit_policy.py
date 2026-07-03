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


def blocks_layer_translate_action(
        transform_type: TransformType,
        space: Space,
        action: ControlPointAction,
        view_type: ViewType | None = None) -> bool:
    """True when a whole-layer translate action must be ignored on the fixed panel."""
    if not fixed_image_manipulation_locked(transform_type, space, view_type):
        return False
    return action in (ControlPointAction.TRANSLATE, ControlPointAction.TRANSLATE_ALL)
