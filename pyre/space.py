import enum


class Space(enum.IntFlag):
    """Indicates whether data is in source or target space"""
    Source = 1
    Target = 2
    Composite = 3  # Both source and target space
