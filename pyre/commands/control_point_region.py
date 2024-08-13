from pyre.state.roi_manager import IRegion, InteractionCandidate, IRegionManager, SelectionEventData
from pyre.commands.interfaces import ICommand
import nornir_imageregistration
from nornir_imageregistration import PointLike


class ControlPointRegion(IRegion):
    """A clickable region to adjust a control point"""

    def __init__(self, control_point: PointLike):
        self._control_point = control_point

    @property
    def bounding_box(self) -> nornir_imageregistration.Rectangle:
        return self._control_point.bounding_box

    def HasInteraction(self, world_position: PointLike) -> float:
        return self._control_point.bounding_box.DistanceToPoint(world_position)

    def GetInteractiveCommandForPosition(self, event: SelectionEventData) -> ICommand | None:
        return None
