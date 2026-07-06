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


def is_geometry_valid(geom: WindowGeometry, screens) -> bool:
    """Return True when *geom* is large enough and intersects an available screen."""
    if geom.width < _MIN_WINDOW_SIZE or geom.height < _MIN_WINDOW_SIZE:
        return False
    rect = QRect(geom.x, geom.y, geom.width, geom.height)
    for screen in screens:
        if rect.intersects(screen.availableGeometry()):
            return True
    return False


def _geometry_from_widget(widget: QWidget) -> WindowGeometry:
    frame = widget.frameGeometry()
    return WindowGeometry(
        x=frame.x(),
        y=frame.y(),
        width=frame.width(),
        height=frame.height(),
        visible=widget.isVisible(),
    )


def _apply_geometry_to_widget(
        widget: QWidget,
        geom: WindowGeometry,
        *,
        visible: bool | None = None) -> None:
    """Restore frame geometry; *visible* overrides saved visibility when set."""
    widget.setGeometry(geom.x, geom.y, geom.width, geom.height)
    widget.setVisible(geom.visible if visible is None else visible)


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
        _apply_geometry_to_widget(window_manager[key], saved[key], visible=True)
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

    if not is_geometry_valid(geom, QGuiApplication.screens()):
        return False

    _apply_geometry_to_widget(browser, geom, visible=True if force_visible else None)
    return True


def has_saved_browser_geometry(settings: AppSettings) -> bool:
    """True when settings contain valid saved geometry for the folder browser."""
    geom = settings.ui.window_geometry.get(STOS_BROWSER_KEY)
    if geom is None:
        return False

    from PyQt6.QtGui import QGuiApplication

    return is_geometry_valid(geom, QGuiApplication.screens())


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
