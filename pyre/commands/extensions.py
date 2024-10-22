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


def GetMouseModifiers(event: wx.MouseEvent) -> InputModifiers:
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

    return modifiers
