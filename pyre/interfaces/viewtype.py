import enum


class ViewType(enum.StrEnum):
    """Helper to identify views"""
    Fixed = "Source"
    Warped = "Target"
    Composite = "Composite"
    Source = "Source"
    Target = "Target"


def convert_to_key(key: str | enum.Enum) -> str:
    """Converts a key to a stable string key.

    For Enum values we prefer the underlying string value (e.g. ViewType.Source -> "Source")
    instead of enum member name (which can be an alias like "Fixed").
    """
    if isinstance(key, enum.Enum):
        value = key.value
        if isinstance(value, str):
            return value
        return key.name
    if isinstance(key, str):
        return key
    raise TypeError(f"key must be a string or ViewType, not {type(key)}")
