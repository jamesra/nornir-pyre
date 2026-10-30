from pyre.interfaces import ICommand
from pyre.interfaces.managers.region_manager import IRegion, SelectionEventData
from typing import Protocol, cast

import nornir_imageregistration
from nornir_imageregistration import PointLike


class _SupportsBoundingBox(Protocol):
    def DistanceToPoint(self, world_position: PointLike) -> float: ...


class _HasBoundingBox(Protocol):
    @property
    def bounding_box(self) -> _SupportsBoundingBox: ...


class ControlPointRegion(IRegion):
    """A clickable region to adjust a control point"""

    def __init__(self, control_point: _HasBoundingBox):
        self._control_point = control_point

    @property
    def bounding_box(self) -> nornir_imageregistration.Rectangle:
        return cast(nornir_imageregistration.Rectangle, self._control_point.bounding_box)

    def interaction_distance(self, world_position: PointLike) -> float:
        return self._control_point.bounding_box.DistanceToPoint(world_position)

    def GetInteractiveCommandForPosition(self, event: SelectionEventData) -> ICommand | None:
        return None
