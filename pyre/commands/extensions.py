"""Helper functions for converting Qt events to Pyre InputEvents."""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QMouseEvent, QKeyEvent, QWheelEvent
from pyre.selection_event_data import InputEvent, InputModifiers


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
