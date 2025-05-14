import enum


class Space(enum.IntFlag):
    """Indicates whether data is in source or target space
    Because Source=0 and Target=1, it is intended this enum can also be used as an argument
    when a tween value is expected for points partially transformed between source and target space
    """
    Source = 0  # Source space
    Target = 1  # Target space

    # Do not add composite as a space, it is a ViewType
