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


@dataclasses.dataclass
class SelectionEventData:
    """Describes an input event that triggers a selection"""

    camera: "pyre.ui.Camera"  # Describes the camera state at the time of the event
    source: InputSource
    input: InputEvent
    modifiers: InputModifiers
    position: NDArray[np.floating]  # The position of the event

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
            InputModifiers.MiddleMouseButton in self.modifiers

    @property
    def IsRightMousePressed(self) -> bool:
        return self.source == InputSource.Mouse and \
            InputModifiers.RightMouseButton in self.modifiers

    @property
    def IsBackMousePressed(self) -> bool:
        return self.source == InputSource.Mouse and \
            InputModifiers.BackMouseButton in self.modifiers

    @property
    def IsForwardMousePressed(self) -> bool:
        return self.source == InputSource.Mouse and \
            InputModifiers.ForwardMouseButton in self.modifiers

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
    ControlKey = 2
    AltKey = 4
    MetaKey = 8
    LeftMouseButton = 16
    MiddleMouseButton = 32
    RightMouseButton = 64
    BackMouseButton = 128
    ForwardMouseButton = 256


class InputSource(enum.Enum):
    """Type of input"""
    Mouse = 1
    Touch = 2
    Pen = 3
    Keyboard = 4
