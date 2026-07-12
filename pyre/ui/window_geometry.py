"""Persist and restore main-window geometry via AppSettings."""

from __future__ import annotations

from PyQt6.QtCore import QRect
from PyQt6.QtWidgets import QMainWindow, QWidget

from pyre.interfaces.managers.window_manager import IWindowManager
from pyre.interfaces.viewtype import ViewType
from pyre.settings.app import AppSettings, WindowGeometry

STOS_WINDOW_KEYS: tuple[str, ...] = ("Source", "Target", "Composite")
STOS_BROWSER_KEY = "StosBrowser"
_MIN_WINDOW_SIZE = 100


def _frame_rect(geom: WindowGeometry) -> QRect:
    return QRect(geom.x, geom.y, geom.width, geom.height)


def _target_available_rect(frame: QRect, screens) -> QRect:
    """Pick the screen work area for *frame* (center match, else primary)."""
    center = frame.center()
    for screen in screens:
        available = screen.availableGeometry()
        if available.contains(center):
            return available
    if screens:
        return screens[0].availableGeometry()
    return QRect(0, 0, 1920, 1080)


def is_geometry_valid(geom: WindowGeometry, screens) -> bool:
    """Return True when *geom* is large enough and its title bar is on-screen."""
    if geom.width < _MIN_WINDOW_SIZE or geom.height < _MIN_WINDOW_SIZE:
        return False
    frame = _frame_rect(geom)
    for screen in screens:
        available = screen.availableGeometry()
        if not frame.intersects(available):
            continue
        if frame.top() < available.top():
            continue
        return True
    return False


def clamp_frame_geometry(geom: WindowGeometry, screens) -> WindowGeometry:
    """Shift or shrink *geom* so the frame fits inside a screen work area."""
    frame = _frame_rect(geom)
    available = _target_available_rect(frame, screens)

    x, y, width, height = frame.x(), frame.y(), frame.width(), frame.height()

    if width > available.width():
        width = available.width()
    if height > available.height():
        height = available.height()

    if x < available.left():
        x = available.left()
    if y < available.top():
        y = available.top()
    if x + width > available.right() + 1:
        x = available.right() + 1 - width
    if y + height > available.bottom() + 1:
        y = available.bottom() + 1 - height

    if x < available.left():
        x = available.left()
    if y < available.top():
        y = available.top()

    width = max(_MIN_WINDOW_SIZE, min(width, available.width()))
    height = max(_MIN_WINDOW_SIZE, min(height, available.height()))

    return geom.model_copy(update={"x": x, "y": y, "width": width, "height": height})


def _geometry_from_widget(widget: QWidget) -> WindowGeometry:
    frame = widget.frameGeometry()
    return WindowGeometry(
        x=frame.x(),
        y=frame.y(),
        width=frame.width(),
        height=frame.height(),
        visible=widget.isVisible(),
    )


def _set_widget_frame_geometry(widget: QWidget, frame: QRect) -> None:
    """Position *widget* so its outer frame matches *frame* (PyQt6 has no setFrameGeometry)."""
    current_frame = widget.frameGeometry()
    current_geom = widget.geometry()
    frame_dx = current_frame.x() - current_geom.x()
    frame_dy = current_frame.y() - current_geom.y()
    frame_dw = current_frame.width() - current_geom.width()
    frame_dh = current_frame.height() - current_geom.height()
    widget.setGeometry(
        frame.x() - frame_dx,
        frame.y() - frame_dy,
        frame.width() - frame_dw,
        frame.height() - frame_dh,
    )


def _apply_geometry_to_widget(
        widget: QWidget,
        geom: WindowGeometry,
        *,
        visible: bool | None = None,
        screens=None) -> None:
    """Restore frame geometry; *visible* overrides saved visibility when set."""
    if screens is None:
        from PyQt6.QtGui import QGuiApplication
        screens = QGuiApplication.screens()

    clamped = clamp_frame_geometry(geom, screens)
    _set_widget_frame_geometry(
        widget, QRect(clamped.x, clamped.y, clamped.width, clamped.height))
    widget.setVisible(clamped.visible if visible is None else visible)


def capture_window_geometry(settings: AppSettings, window_manager: IWindowManager) -> None:
    """Write current window frames into ``settings.ui.window_geometry``."""
    saved: dict[str, WindowGeometry] = {}
    for key in STOS_WINDOW_KEYS:
        view_type = ViewType(key)
        if view_type not in window_manager:
            continue
        saved[key] = _geometry_from_widget(window_manager[view_type])
        # Layout windows are hidden on File→Exit; always persist visible so the next
        # launch restores position/size without leaving all views off-screen/invisible.
        saved[key] = saved[key].model_copy(update={"visible": True})

    from pyre.ui.windows.stoswindow import StosWindow

    browser = StosWindow._folder_browser
    if browser is not None:
        saved[STOS_BROWSER_KEY] = _geometry_from_widget(browser)

    settings.ui.window_geometry = saved


def _stos_geometry_restorable(saved: dict[str, WindowGeometry], screens) -> bool:
    for key in STOS_WINDOW_KEYS:
        if key not in saved:
            return False
        if not is_geometry_valid(saved[key], screens):
            return False
    return True


def apply_saved_window_geometry(settings: AppSettings, window_manager: IWindowManager) -> bool:
    """Restore Source/Target/Composite geometry when all three entries are valid."""
    saved = settings.ui.window_geometry
    if not saved:
        return False

    from PyQt6.QtGui import QGuiApplication

    screens = QGuiApplication.screens()
    if not _stos_geometry_restorable(saved, screens):
        return False

    for key in STOS_WINDOW_KEYS:
        _apply_geometry_to_widget(window_manager[key], saved[key], visible=True, screens=screens)
    return True


def apply_saved_browser_geometry(
        settings: AppSettings,
        browser: QMainWindow,
        *,
        force_visible: bool = False) -> bool:
    """Restore folder-browser geometry when a valid saved entry exists."""
    saved = settings.ui.window_geometry
    geom = saved.get(STOS_BROWSER_KEY)
    if geom is None:
        return False

    from PyQt6.QtGui import QGuiApplication

    screens = QGuiApplication.screens()
    if not is_geometry_valid(geom, screens):
        return False

    _apply_geometry_to_widget(browser, geom, visible=True if force_visible else None, screens=screens)
    return True


def has_saved_browser_geometry(settings: AppSettings) -> bool:
    """True when settings contain valid saved geometry for the folder browser."""
    geom = settings.ui.window_geometry.get(STOS_BROWSER_KEY)
    if geom is None:
        return False

    from PyQt6.QtGui import QGuiApplication

    return is_geometry_valid(geom, QGuiApplication.screens())


def apply_frame_geometry_to_widget(
        widget: QWidget,
        x: int,
        y: int,
        width: int,
        height: int,
        *,
        screens=None) -> None:
    """Set a widget's frame geometry, clamped to visible screen work areas."""
    geom = WindowGeometry(x=x, y=y, width=width, height=height, visible=True)
    _apply_geometry_to_widget(widget, geom, visible=None, screens=screens)


def restore_or_default_layout(
        settings: AppSettings,
        window_manager: IWindowManager,
        anchor_window: QMainWindow) -> bool:
    """Apply saved geometry or fall back to monitor-based presets."""
    del anchor_window  # kept for call-site compatibility
    if apply_saved_window_geometry(settings, window_manager):
        return True
    for key in STOS_WINDOW_KEYS:
        window_manager[key].setPosition()
    return False
