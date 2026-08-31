from enum import Enum


class OverlayType(Enum):
    Tween = 0,  # Blend the textures using the tween value
    ChannelDodge = 1,  # Put textures into separate channels
    Difference = 2,  # Subtract one texture from another
