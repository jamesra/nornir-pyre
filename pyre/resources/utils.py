import os


def try_locate_file(ImageFullPath: str, listAltDirs: list[str]) -> str | None:
    """
    If the image path is not a file this function searches the list of directories for the image file in order.
    :returns: The full path to the image file if found, otherwise None.
    """
    if os.path.exists(ImageFullPath):
        return ImageFullPath
    else:
        filename = ImageFullPath

        # Do not use the base filename if the ImagePath is relative
        if os.path.isabs(ImageFullPath):
            filename = os.path.basename(ImageFullPath)

        for dirname in listAltDirs:
            next_path = os.path.join(dirname, filename)
            if os.path.exists(next_path):
                return next_path

    return None
