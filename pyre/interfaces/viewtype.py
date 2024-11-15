import enum


class ViewType(enum.StrEnum):
    """Helper to identify views"""
    Fixed = "Source"
    Warped = "Target"
    Composite = "Composite"
    Source = "Source"
    Target = "Target"


def convert_to_key(key: str | enum.Enum) -> str:
    """Converts a key to a string"""
    if isinstance(key, str):
        return key
    elif isinstance(key, enum.Enum):
        return key.name
    else:
        raise TypeError(f"key must be a string or ViewType, not {type(key)}")
