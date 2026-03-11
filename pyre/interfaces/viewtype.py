import enum


class ViewType(enum.StrEnum):
    """Helper to identify views"""
    Fixed = "Source"
    Warped = "Target"
    Composite = "Composite"
    Source = "Source"
    Target = "Target"


def convert_to_key(key: str | enum.Enum) -> str:
    """Converts a key to a string. Enum is checked before str so StrEnum (subclass of str) returns .name."""
    if isinstance(key, enum.Enum):
        return key.name
    if isinstance(key, str):
        return key
    raise TypeError(f"key must be a string or ViewType, not {type(key)}")
