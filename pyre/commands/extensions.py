"""Helper functions for converting Qt events to Pyre InputEvents."""

from PyQt6.QtCore import Qt, QEvent
from PyQt6.QtGui import QMouseEvent, QKeyEvent, QWheelEvent
from pyre.selection_event_data import InputEvent, InputModifiers

# Roughly one mouse-wheel notch when platforms report pixelDelta instead of angleDelta.
_PIXEL_DELTA_PER_NOTCH = 15.0


def wheel_scroll_steps(event: QWheelEvent) -> float:
    """Return wheel motion in standard-notch units (1.0 ≈ one detent).

    Qt may leave angleDelta at zero for high-resolution / modifier wheel events on
    Windows; fall back to pixelDelta in that case.
    """
    angle_y = event.angleDelta().y()
    if angle_y != 0:
        return angle_y / 120.0
    pixel_y = event.pixelDelta().y()
    if pixel_y != 0:
        return pixel_y / _PIXEL_DELTA_PER_NOTCH
    return 0.0


def GetKeyModifiers(event: QMouseEvent | QKeyEvent | QWheelEvent) -> InputModifiers:
    modifiers = InputModifiers.NoModifiers
    if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
        modifiers |= InputModifiers.ShiftKey
    if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
        modifiers |= InputModifiers.ControlKey
    if event.modifiers() & Qt.KeyboardModifier.AltModifier:
        modifiers |= InputModifiers.AltKey
    if event.modifiers() & Qt.KeyboardModifier.MetaModifier:
        modifiers |= InputModifiers.MetaKey
    return modifiers


def GetMouseModifiers(event: QMouseEvent | QWheelEvent, last_mouse_event: QMouseEvent | QWheelEvent | None = None) -> InputModifiers:
    modifiers = GetKeyModifiers(event)

    # Check mouse buttons only for QMouseEvent
    if isinstance(event, QMouseEvent):
        if event.buttons() & Qt.MouseButton.LeftButton:
            modifiers |= InputModifiers.LeftMouseButton
        if event.buttons() & Qt.MouseButton.MiddleButton:
            modifiers |= InputModifiers.MiddleMouseButton
        if event.buttons() & Qt.MouseButton.RightButton:
            modifiers |= InputModifiers.RightMouseButton
        if event.buttons() & Qt.MouseButton.BackButton:
            modifiers |= InputModifiers.BackMouseButton
        if event.buttons() & Qt.MouseButton.ForwardButton:
            modifiers |= InputModifiers.ForwardMouseButton
        # Qt reports buttons() after the event. On release the released button is
        # in button(), not buttons(), so last-event comparison can miss the change.
        if event.type() == QEvent.Type.MouseButtonRelease:
            if event.button() == Qt.MouseButton.LeftButton:
                modifiers |= InputModifiers.LeftMouseButtonChanged
            elif event.button() == Qt.MouseButton.MiddleButton:
                modifiers |= InputModifiers.MiddleMouseButtonChanged
            elif event.button() == Qt.MouseButton.RightButton:
                modifiers |= InputModifiers.RightMouseButtonChanged
            elif event.button() == Qt.MouseButton.BackButton:
                modifiers |= InputModifiers.BackMouseButtonChanged
            elif event.button() == Qt.MouseButton.ForwardButton:
                modifiers |= InputModifiers.ForwardMouseButtonChanged

    # Check wheel rotation for QWheelEvent
    if isinstance(event, QWheelEvent):
        if event.angleDelta().y() > 0:
            modifiers |= InputEvent.ScrollUp  # type: ignore[operator]
        elif event.angleDelta().y() < 0:
            modifiers |= InputEvent.ScrollDown  # type: ignore[operator]

    # Compare with last event if available
    if last_mouse_event is not None and isinstance(event, QMouseEvent) and isinstance(last_mouse_event, QMouseEvent):
        if (event.buttons() & Qt.MouseButton.LeftButton) != (last_mouse_event.buttons() & Qt.MouseButton.LeftButton):
            modifiers |= InputModifiers.LeftMouseButtonChanged
        if (event.buttons() & Qt.MouseButton.MiddleButton) != (last_mouse_event.buttons() & Qt.MouseButton.MiddleButton):
            modifiers |= InputModifiers.MiddleMouseButtonChanged
        if (event.buttons() & Qt.MouseButton.RightButton) != (last_mouse_event.buttons() & Qt.MouseButton.RightButton):
            modifiers |= InputModifiers.RightMouseButtonChanged
        if (event.buttons() & Qt.MouseButton.BackButton) != (last_mouse_event.buttons() & Qt.MouseButton.BackButton):
            modifiers |= InputModifiers.BackMouseButtonChanged
        if (event.buttons() & Qt.MouseButton.ForwardButton) != (last_mouse_event.buttons() & Qt.MouseButton.ForwardButton):
            modifiers |= InputModifiers.ForwardMouseButtonChanged

    return modifiers
