from __future__ import annotations

from typing import NamedTuple
import dataclasses
import enum
from pyre.space import Space

import numpy as np
from numpy._typing import NDArray
from pygame.pypm import Input

from pyre.observable import ObservableSet


# from pyre.ui import Camera


class PointPair(NamedTuple):
    target: NDArray[[2, ], np.floating]
    source: NDArray[[2, ], np.floating]

    def __getitem__(self, key: Space) -> NDArray[[2, ], np.floating]:
        if key == Space.Source:
            return self.source
        elif key == Space.Target:
            return self.target
        else:
            raise ValueError(f"Invalid key {key}")


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
    keycode: int | None = None  # The key code for keyboard events
    existing_selections: ObservableSet[
        int] = None  # The indices of currently selected points.  Some commands need a single selection and this is used to determine if those commands can be activated

    @property
    def eventkey(self) -> SelectionEventKey:
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
    def IsOnlyShiftPressed(self) -> bool:
        return InputModifiers.is_only_one_key_modifier_set(self.modifiers, InputModifiers.ShiftKey)

    @property
    def IsAltPressed(self) -> bool:
        return InputModifiers.AltKey in self.modifiers

    @property
    def IsOnlyAltPressed(self) -> bool:
        return InputModifiers.is_only_one_key_modifier_set(self.modifiers, InputModifiers.AltKey)

    @property
    def IsCtrlPressed(self) -> bool:
        return InputModifiers.ControlKey in self.modifiers

    @property
    def IsOnlyCtrlPressed(self) -> bool:
        return InputModifiers.is_only_one_key_modifier_set(self.modifiers, InputModifiers.ControlKey)

    @property
    def IsMetaPressed(self) -> bool:
        return InputModifiers.MetaKey in self.modifiers

    @property
    def IsOnlyMetaPressed(self) -> bool:
        return InputModifiers.is_only_one_key_modifier_set(self.modifiers, InputModifiers.MetaKey)

    @property
    def NoModifierKeys(self) -> bool:
        """Returns true if no modifier keys are pressed"""
        return InputModifiers.KeyboardModifiers & self.modifiers == InputModifiers.NoModifiers

    def IsKeyChordPressed(self, chord: InputModifiers) -> bool:
        """Returns true if only the specified keys are pressed, ignores changed flags"""
        return InputModifiers.is_key_chord_pressed(self.modifiers, chord)

    def IsChordPressed(self, chord: InputModifiers) -> bool:
        """Returns true if only the specified mouse/key buttons are pressed, ignores changed flags"""
        return InputModifiers.is_chord_pressed(self.modifiers, chord)


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
    KeyboardModifiers = ShiftKey | ControlKey | AltKey | MetaKey  # Modifiers for keyboard events
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
    MouseModifiers = LeftMouseButton | MiddleMouseButton | RightMouseButton | BackMouseButton | ForwardMouseButton  # Modifiers for mouse events

    @staticmethod
    def is_only_one_key_modifier_set(modifiers: InputModifiers, key: InputModifiers) -> bool:
        """Check if only one flag is set in the enum.Flag"""
        return modifiers & InputModifiers.KeyboardModifiers == key

    @staticmethod
    def is_only_one_mouse_button_pressed(modifiers: InputModifiers, button: InputModifiers) -> bool:
        """Check if only one flag is set in the enum.Flag"""
        return modifiers & InputModifiers.MouseModifiers == button

    @staticmethod
    def is_chord_pressed(modifiers: InputModifiers, chord: InputModifiers) -> bool:
        """Returns true if only the specified mouse/key buttons are pressed, ignores changed flags"""
        return modifiers & (InputModifiers.KeyboardModifiers | InputModifiers.MouseModifiers) == chord

    @staticmethod
    def is_key_chord_pressed(modifiers: InputModifiers, chord: InputModifiers) -> bool:
        """Returns true if only the specified mouse/key buttons are pressed, ignores changed flags"""
        return modifiers & InputModifiers.KeyboardModifiers == chord

    @staticmethod
    def is_mouse_chord_pressed(modifiers: InputModifiers, chord: InputModifiers) -> bool:
        """Returns true if only the specified mouse/key buttons are pressed, ignores changed flags"""
        return modifiers & InputModifiers.MouseModifiers == chord


class InputSource(enum.Enum):
    """Type of input"""
    Mouse = 1
    Touch = 2
    Pen = 3
    Keyboard = 4
