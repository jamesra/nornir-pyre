from __future__ import annotations

from typing import NamedTuple
import dataclasses
import enum

import numpy as np
from numpy._typing import NDArray


# from pyre.ui import Camera


class PointPair(NamedTuple):
    target: NDArray[[2, ], np.floating]
    source: NDArray[[2, ], np.floating]


class SelectionEventKey(NamedTuple):
    """A key for storing historical event information by source and input type"""
    source: InputSource
    input: InputEvent


@dataclasses.dataclass
class SelectionEventData:
    """Describes an input event that triggers a selection"""

    camera: "pyre.ui.Camera"  # Describes the camera state at the time of the event
    source: InputSource
    input: InputEvent
    modifiers: InputModifiers
    position: NDArray[np.floating]  # The position of the event

    @property
    def key(self) -> SelectionEventKey:
        """:return: A key for this event based on source and input type"""
        return SelectionEventKey(self.source, self.input)

    @property
    def IsMouseInput(self) -> bool:
        return self.source == InputSource.Mouse

    @property
    def IsKeyboardInput(self) -> bool:
        return self.source == InputSource.Keyboard

    @property
    def IsPenInput(self) -> bool:
        return self.source == InputSource.Pen

    @property
    def IsLeftMousePressed(self) -> bool:
        return self.source == InputSource.Mouse and \
            self.modifiers & InputModifiers.LeftMouseButton

    @property
    def IsMiddleMousePressed(self) -> bool:
        return self.source == InputSource.Mouse and \
            InputModifiers.MiddleMouseButton & self.modifiers

    @property
    def IsRightMousePressed(self) -> bool:
        return self.source == InputSource.Mouse and \
            InputModifiers.RightMouseButton & self.modifiers

    @property
    def IsBackMousePressed(self) -> bool:
        return self.source == InputSource.Mouse and \
            InputModifiers.BackMouseButton & self.modifiers

    @property
    def IsForwardMousePressed(self) -> bool:
        return self.source == InputSource.Mouse and \
            InputModifiers.ForwardMouseButton & self.modifiers

    @property
    def IsLeftMouseChanged(self) -> bool:
        return self.source == InputSource.Mouse and \
            self.modifiers & InputModifiers.LeftMouseButtonChanged

    @property
    def IsMiddleMouseChanged(self) -> bool:
        return self.source == InputSource.Mouse and \
            InputModifiers.MiddleMouseButtonChanged & self.modifiers

    @property
    def IsRightMouseChanged(self) -> bool:
        return self.source == InputSource.Mouse and \
            InputModifiers.RightMouseButtonChanged & self.modifiers

    @property
    def IsBackMouseChanged(self) -> bool:
        return self.source == InputSource.Mouse and \
            InputModifiers.BackMouseButtonChanged & self.modifiers

    @property
    def IsForwardMouseChanged(self) -> bool:
        return self.source == InputSource.Mouse and \
            InputModifiers.ForwardMouseButtonChanged & self.modifiers

    @property
    def IsShiftPressed(self) -> bool:
        return InputModifiers.ShiftKey in self.modifiers

    @property
    def IsAltPressed(self) -> bool:
        return InputModifiers.AltKey in self.modifiers

    @property
    def IsCtrlPressed(self) -> bool:
        return InputModifiers.ControlKey in self.modifiers

    @property
    def IsMetaPressed(self) -> bool:
        return InputModifiers.MetaKey in self.modifiers


class InputEvent(enum.Enum):
    """Events that can trigger a selection"""
    Press = 1
    Release = 2
    Drag = 3
    ScrollUp = 4
    ScrollDown = 5


class InputModifiers(enum.Flag):
    """Modifiers that are active during the event"""
    NoModifiers = 0
    ShiftKey = 1
    ControlKey = 1 << 1
    AltKey = 1 << 2
    MetaKey = 1 << 3
    LeftMouseButton = 1 << 4  # True if the button is pressed
    MiddleMouseButton = 1 << 5
    RightMouseButton = 1 << 6
    BackMouseButton = 1 << 7
    ForwardMouseButton = 1 << 8
    LeftMouseButtonChanged = 1 << 9  # True if the button state changed from the last press/release event
    MiddleMouseButtonChanged = 1 << 10
    RightMouseButtonChanged = 1 << 11
    BackMouseButtonChanged = 1 << 12
    ForwardMouseButtonChanged = 1 << 13


class InputSource(enum.Enum):
    """Type of input"""
    Mouse = 1
    Touch = 2
    Pen = 3
    Keyboard = 4
