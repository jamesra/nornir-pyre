"""Whether a control point currently falls inside a STOS panel camera."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

import numpy as np
from numpy.typing import NDArray

import nornir_imageregistration
from pyre.interfaces.viewtype import ViewType
from pyre.space import Space

if TYPE_CHECKING:
    from pyre.controllers.transformcontroller import TransformController
    from pyre.ui.camera import Camera


class _WindowLookup(Protocol):
    def __contains__(self, key: object) -> bool: ...
    def __getitem__(self, key: object) -> object: ...


def point_yx_in_camera_view(
        point_yx: NDArray[np.floating],
        camera: Camera,
) -> bool:
    """True when world *point_yx* lies inside *camera*'s visible image bounding box."""
    yx = np.asarray(point_yx, dtype=np.float64).reshape(-1)
    if yx.size < 2 or not np.all(np.isfinite(yx[:2])):
        return False
    bbox = camera.VisibleImageBoundingBox
    return bool(nornir_imageregistration.Rectangle.contains(bbox, yx[:2]))


def control_point_visible_in_stos_views(
        controller: TransformController,
        index: int,
        window_manager: _WindowLookup | None = None,
) -> bool:
    """True if control-point *index* is inside any visible STOS panel camera.

    Headless callers (no window manager, or no visible STOS windows) treat the
    point as visible so selection restore still works in tests.
    """
    manager = window_manager
    if manager is None:
        import pyre.state
        config = pyre.state.get_current_stos_config()
        manager = None if config is None else config.window_manager
    if manager is None:
        return True

    from pyre.viewmodels.controlpointmap import ControlPointMap

    saw_visible_window = False
    for view_type in (ViewType.Source, ViewType.Target, ViewType.Composite):
        if view_type not in manager:
            continue
        window = manager[view_type]
        if not getattr(window, "isVisible", lambda: False)():
            continue
        panel = getattr(window, "imagepanel", None)
        camera = None if panel is None else getattr(panel, "camera", None)
        if camera is None:
            continue
        saw_visible_window = True
        space = getattr(panel, "space", Space.Target)
        points = ControlPointMap.tweened_points(controller, space, view_type)
        if index < 0 or index >= int(points.shape[0]):
            continue
        if point_yx_in_camera_view(points[index], camera):
            return True
    return not saw_visible_window
