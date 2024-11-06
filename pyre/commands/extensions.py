"""Helper functions for converting wxPython events to Pyre InputEvents."""

import wx
from pyre.selection_event_data import InputEvent, InputModifiers


def GetKeyModifiers(event: wx.MouseEvent) -> InputModifiers:
    modifiers = InputModifiers.NoModifiers
    if event.ShiftDown():
        modifiers |= InputModifiers.ShiftKey
    if event.ControlDown():
        modifiers |= InputModifiers.ControlKey
    if event.AltDown():
        modifiers |= InputModifiers.AltKey
    if event.MetaDown():
        modifiers |= InputModifiers.MetaKey
    return modifiers


def GetMouseModifiers(event: wx.MouseEvent, last_mouse_event: wx.MouseEvent = None) -> InputModifiers:
    modifiers = GetKeyModifiers(event)
    if event.LeftIsDown():
        modifiers |= InputModifiers.LeftMouseButton
    if event.MiddleIsDown():
        modifiers |= InputModifiers.MiddleMouseButton
    if event.RightIsDown():
        modifiers |= InputModifiers.RightMouseButton
    if event.Aux1IsDown():
        modifiers |= InputModifiers.BackMouseButton
    if event.Aux2IsDown():
        modifiers |= InputModifiers.ForwardMouseButton
    if event.GetWheelRotation() > 0:
        modifiers |= InputEvent.ScrollUp
    elif event.GetWheelRotation() < 0:
        modifiers |= InputEvent.ScrollDown

    if last_mouse_event is not None:
        if event.LeftIsDown() != last_mouse_event.LeftIsDown():
            modifiers |= InputModifiers.LeftMouseButtonChanged
        if event.MiddleIsDown() != last_mouse_event.MiddleIsDown():
            modifiers |= InputModifiers.MiddleMouseButtonChanged
        if event.RightIsDown() != last_mouse_event.RightIsDown():
            modifiers |= InputModifiers.RightMouseButtonChanged
        if event.Aux1IsDown() != last_mouse_event.Aux1IsDown():
            modifiers |= InputModifiers.BackMouseButtonChanged
        if event.Aux2IsDown() != last_mouse_event.Aux2IsDown():
            modifiers |= InputModifiers.ForwardMouseButtonChanged

    return modifiers
