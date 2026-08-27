from __future__ import annotations

import enum

from dependency_injector.wiring import inject, Provide
import numpy as np
from numpy.typing import NDArray
from PyQt6.QtCore import Qt, QPoint, QRect, QSize
from PyQt6.QtGui import QMouseEvent, QKeyEvent, QPainter, QPen, QColor, QPolygon, QPaintEvent, QCursor
from PyQt6.QtWidgets import QWidget, QRubberBand

import nornir_imageregistration
from nornir_imageregistration.transforms import IControlPoints
from pyre.observable import ObservableSet, SetOperation
from pyre import Space
from pyre.interfaces import StatusChangeCallback
from pyre.commands import NavigationCommandBase
from pyre.commands.togglecontrolpointselectioncommand import apply_selection_set_operation
from pyre.interfaces.managers import ICommandQueue, IControlPointMapManager, ControlPointManagerKey
from pyre.interfaces.viewtype import ViewType
from pyre.container import IContainer
from pyre.selection_event_data import PointPair
from pyre.viewmodels.controlpointmap import ControlPointMap
from pyre.views.gltiles import is_rigid_transform
import pyre.ui
from pyre.controllers.transformcontroller import TransformController


class RegionSelectShape(enum.Enum):
    BOX = "box"
    LASSO = "lasso"


class _LassoOverlay(QWidget):
    """Mouse-transparent polyline drawn over the GL panel during lasso select."""

    _path: list[QPoint]

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._path = []
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setGeometry(parent.rect())
        self.show()
        self.raise_()

    def set_path(self, path: list[QPoint]) -> None:
        self._path = path
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        if len(self._path) < 2:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(255, 220, 0, 230), 1, Qt.PenStyle.DashLine))
        painter.drawPolyline(QPolygon(self._path))
        if len(self._path) >= 3:
            painter.drawLine(self._path[-1], self._path[0])


def indices_in_region(
        control_point_map: ControlPointMap,
        shape: RegionSelectShape,
        world_points: NDArray[np.floating],
) -> set[int]:
    """Return control-point indices inside a box (two corners) or lasso polygon."""
    pts = np.asarray(world_points, dtype=np.float64).reshape(-1, 2)
    if shape == RegionSelectShape.BOX:
        if pts.shape[0] < 2:
            return set()
        return control_point_map.find_in_rect(pts[0], pts[-1])
    if pts.shape[0] < 3:
        return set()
    return control_point_map.find_in_polygon(pts)


class RegionSelectCommand(NavigationCommandBase):
    """Drag a box or lasso over control points, then replace or shift-add/remove the selection."""

    _selected_points: ObservableSet[int]
    _space: Space
    _shape: RegionSelectShape
    _set_operation: SetOperation
    _origin_qt: tuple[float, float] | None
    _path_qt: list[tuple[float, float]]
    _rubber_band: QRubberBand | None
    _lasso_overlay: _LassoOverlay | None
    _controlpointmap: ControlPointMap | None
    _controlpointmap_manager: IControlPointMapManager = Provide[IContainer.control_point_map_manager]

    @inject
    def __init__(
            self,
            parent: QWidget,
            camera: pyre.ui.Camera,
            bounds: nornir_imageregistration.Rectangle,
            selected_points: ObservableSet[int],
            space: Space,
            commandqueue: ICommandQueue,
            shape: RegionSelectShape = RegionSelectShape.BOX,
            set_operation: SetOperation = SetOperation.Replace,
            region_origin_qt: tuple[float, float] | None = None,
            completed_func: StatusChangeCallback | None = None,
            transform_controller: TransformController = Provide[IContainer.transform_controller],
            **kwargs,
    ) -> None:
        super().__init__(
            parent,
            transform_controller=transform_controller,
            camera=camera,
            bounds=bounds,
            space=space,
            commandqueue=commandqueue,
            completed_func=completed_func,
        )
        self._selected_points = selected_points
        self._space = space
        self._shape = shape
        self._set_operation = set_operation
        self._origin_qt = region_origin_qt
        self._path_qt = [] if region_origin_qt is None else [region_origin_qt]
        self._rubber_band = None
        self._lasso_overlay = None
        self._controlpointmap = None
        model = transform_controller.TransformModel
        if isinstance(model, IControlPoints):
            key = ControlPointManagerKey(transform_controller, space, self._view_type())
            self._controlpointmap = self._controlpointmap_manager.getorcreate(key)

    def __str__(self) -> str:
        return f"RegionSelectCommand({self._shape.value})"

    def _world_point_for_select(self, point_pair: PointPair) -> NDArray[np.floating]:
        """World coords used for region hit-testing in this panel."""
        model = self._transform_controller.TransformModel
        if (
                self._view_type() == ViewType.Composite
                and model is not None
                and not is_rigid_transform(model)
        ):
            return point_pair.target
        return point_pair.source if self.space == Space.Source else point_pair.target

    def _qt_to_world(self, qt_x: float, qt_y: float) -> NDArray[np.floating]:
        """Map widget (top-left) coordinates to panel world space."""
        point_pair = self.get_world_positions((qt_y, qt_x))
        return np.asarray(self._world_point_for_select(point_pair), dtype=np.float64)

    def _ensure_origin(self, qt_x: float, qt_y: float) -> tuple[float, float]:
        if self._origin_qt is None:
            self._origin_qt = (qt_x, qt_y)
            self._path_qt = [(qt_x, qt_y)]
        return self._origin_qt

    def _sync_overlay_geometry(self) -> None:
        if self._lasso_overlay is not None:
            self._lasso_overlay.setGeometry(self.parent.rect())

    def _show_overlay(self) -> None:
        if self._shape == RegionSelectShape.BOX:
            if self._rubber_band is None:
                self._rubber_band = QRubberBand(QRubberBand.Shape.Rectangle, self.parent)
            origin = self._origin_qt
            if origin is not None:
                ox, oy = int(origin[0]), int(origin[1])
                self._rubber_band.setGeometry(QRect(QPoint(ox, oy), QSize(1, 1)))
            self._rubber_band.show()
            return
        if self._lasso_overlay is None:
            self._lasso_overlay = _LassoOverlay(self.parent)
        self._sync_overlay_geometry()
        self._lasso_overlay.set_path([QPoint(int(x), int(y)) for x, y in self._path_qt])

    def _update_overlay(self, qt_x: float, qt_y: float) -> None:
        origin = self._ensure_origin(qt_x, qt_y)
        if self._shape == RegionSelectShape.BOX:
            self._path_qt = [origin, (qt_x, qt_y)]
            if self._rubber_band is None:
                self._show_overlay()
            assert self._rubber_band is not None
            ox, oy = int(origin[0]), int(origin[1])
            self._rubber_band.setGeometry(QRect(QPoint(ox, oy), QPoint(int(qt_x), int(qt_y))).normalized())
            return
        last = self._path_qt[-1] if self._path_qt else None
        if last is None or abs(last[0] - qt_x) >= 1.0 or abs(last[1] - qt_y) >= 1.0:
            self._path_qt.append((qt_x, qt_y))
        if self._lasso_overlay is None:
            self._show_overlay()
        else:
            self._sync_overlay_geometry()
            self._lasso_overlay.set_path([QPoint(int(x), int(y)) for x, y in self._path_qt])

    def _hide_overlay(self) -> None:
        if self._rubber_band is not None:
            self._rubber_band.hide()
            self._rubber_band.deleteLater()
            self._rubber_band = None
        if self._lasso_overlay is not None:
            self._lasso_overlay.hide()
            self._lasso_overlay.deleteLater()
            self._lasso_overlay = None

    def _world_path(self) -> NDArray[np.floating]:
        if not self._path_qt and self._origin_qt is not None:
            samples = [self._origin_qt]
        else:
            samples = self._path_qt
        if not samples:
            return np.zeros((0, 2), dtype=np.float64)
        return np.vstack([self._qt_to_world(x, y) for x, y in samples])

    def on_activate(self) -> None:
        pos = self.parent.mapFromGlobal(QCursor.pos())
        if self._origin_qt is None:
            self._origin_qt = (float(pos.x()), float(pos.y()))
            self._path_qt = [self._origin_qt]
        self._show_overlay()
        self._update_overlay(float(pos.x()), float(pos.y()))

    def on_mouse_press(self, event: QMouseEvent) -> None:
        if event.buttons() & Qt.MouseButton.RightButton or event.buttons() & Qt.MouseButton.MiddleButton:
            self.cancel()

    def on_mouse_motion(self, event: QMouseEvent) -> None:
        if event.buttons() & Qt.MouseButton.RightButton:
            self.cancel()
            return
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        pos = event.position()
        self._update_overlay(float(pos.x()), float(pos.y()))

    def on_mouse_release(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position()
            self._update_overlay(float(pos.x()), float(pos.y()))
            self.execute()

    def on_mouse_scroll(self, event: QMouseEvent) -> None:
        return

    def on_key_down(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.cancel()

    def on_key_up(self, event: QKeyEvent) -> None:
        return

    def can_execute(self) -> bool:
        return True

    def cancel(self) -> None:
        self._hide_overlay()
        super().cancel()

    def execute(self) -> None:
        try:
            world = self._world_path()
            hits: set[int] = set()
            if self._controlpointmap is not None:
                hits = indices_in_region(self._controlpointmap, self._shape, world)
                apply_selection_set_operation(self._selected_points, hits, self._set_operation)
        finally:
            self._hide_overlay()
            super().execute()

    def subscribe_to_parent(self) -> None:
        self._bind_mouse_events()
        self._saved_mousePressEvent = None
        self._saved_mouseMoveEvent = None
        self._saved_mouseReleaseEvent = None
        self._bind_key_events()

    def unsubscribe_to_parent(self) -> None:
        self._unbind_mouse_events()
        self._unbind_key_events()
        self._hide_overlay()
