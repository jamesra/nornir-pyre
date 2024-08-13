import enum


class Space(enum.IntFlag):
    """Indicates whether data is in source or target space"""
    Source = 1  # Source space
    Target = 2  # Target space
    # Do not add composite as a space, it is a ViewType
