import os


def try_locate_file(ImageFullPath: str, listAltDirs: list[str],
                    replacement_paths: dict[str, str] | None = None) -> str | None:
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
            ImageFullPath = ImageFullPath.lower()

            # Check for replacement paths in order if we have an absolute filename
            if replacement_paths is not None:
                for old_subpath, new_subpath in replacement_paths.items():
                    if old_subpath.lower() in ImageFullPath.lower():
                        new_path = ImageFullPath.lower().replace(old_subpath.lower(), new_subpath.lower())
                        new_path = new_path.replace(new_subpath.lower(),
                                                    new_subpath)  # Fix case just for our replaced path
                        if os.path.exists(new_path):
                            return new_path
            # if '\\\\opr-marc-syn1\\data' in ImageFullPath:
            #     mapdrivepath = ImageFullPath.replace('\\\\opr-marc-syn1\\data', 'X:')
            #     if os.path.exists(mapdrivepath):
            #         return mapdrivepath

        for dirname in listAltDirs:
            next_path = os.path.join(dirname, filename)
            if os.path.exists(next_path):
                return next_path

    return None
