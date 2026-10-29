"""Helper functions for converting Qt events to Pyre InputEvents."""

from PyQt6.QtCore import Qt, QEvent
from PyQt6.QtGui import QMouseEvent, QKeyEvent, QWheelEvent
from pyre.selection_event_data import InputEvent, InputModifiers

# Roughly one mouse-wheel notch when platforms report pixelDelta instead of angleDelta.
_PIXEL_DELTA_PER_NOTCH = 15.0

# One-pixel (dy, dx) step per arrow key: Up is +Y, Right is +X.
_ARROW_KEY_UNIT_YX: dict[int, tuple[int, int]] = {
    Qt.Key.Key_Left: (0, -1),
    Qt.Key.Key_Right: (0, 1),
    Qt.Key.Key_Up: (1, 0),
    Qt.Key.Key_Down: (-1, 0),
}


def arrow_key_nudge_yx(event: QKeyEvent) -> tuple[int, int] | None:
    """Return the (dy, dx) arrow-key nudge for ``event``, or None for any other key.

    Users can nudge with the arrow keys. One press steps one pixel; holding Shift
    steps 5, holding Ctrl steps 25, holding both steps 125. Other modifiers are ignored.
    """
    unit_yx = _ARROW_KEY_UNIT_YX.get(event.key())
    if unit_yx is None:
        return None
    multiplier = 1
    if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
        multiplier *= 5
    if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
        multiplier *= 25
    return unit_yx[0] * multiplier, unit_yx[1] * multiplier


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
