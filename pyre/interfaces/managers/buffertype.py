from __future__ import annotations

import enum

from pyre.gl_engine import GLBuffer


class BufferType(enum.IntEnum):
    """The type of buffer to return"""
    ControlPoint = 1
    Selection = 2


GLBufferCollection = dict[BufferType, GLBuffer]
