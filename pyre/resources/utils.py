import os
from pathlib import PurePath, Path


def _try_rerooted_path(anchor_dir: str, image_fullpath: str) -> str | None:
    """
    Reconstruct an image path when the data tree may have been moved or rerooted.

    Finds the longest prefix of *anchor_dir*'s directory components that
    matches a contiguous run of components inside *image_fullpath*, then
    rebuilds the candidate path as::

        <anchor prefix up to the match> / <image tail after the match>

    This lets Pyre locate images whose absolute paths were recorded on a
    different machine or drive, as long as the .stos file and the images
    share a recognisable ancestor directory name.

    Examples::

        # Same drive – common ancestor is TEM:
        anchor_dir = C:\\TEM\\Brute32
        image      = C:\\TEM\\0001\\Leveled\\16.png
        → C:\\TEM\\0001\\Leveled\\16.png          (identical to original – already tried)

        # Different drive / base – common ancestor is TEM:
        anchor_dir = C:\\TEM\\Brute32
        image      = D:\\OldData\\TEM\\0001\\Leveled\\16.png
        → C:\\TEM\\0001\\Leveled\\16.png          (rerooted onto C:\\TEM)

    Returns ``None`` if no common directory component is found.
    """
    anchor_parts = PurePath(anchor_dir).parts   # e.g. ('C:\\', 'TEM', 'Brute32')
    image_parts = PurePath(image_fullpath).parts  # e.g. ('D:\\', 'OldData', 'TEM', ...)

    # Need at least a drive and one directory component on each side, plus a filename.
    if len(anchor_parts) < 2 or len(image_parts) < 2:
        return None

    # Separate into: root/drive, intermediate directories, filename
    anchor_dirs_lower = [p.lower() for p in anchor_parts[1:]]   # for matching
    anchor_dirs_orig = list(anchor_parts[1:])                    # for path construction

    image_dirs_lower = [p.lower() for p in image_parts[1:-1]]   # dirs only (no drive/filename)
    image_dirs_orig = list(image_parts[1:-1])
    image_filename = image_parts[-1]

    if not image_dirs_lower:
        return None

    # Find the position in image_dirs where the longest prefix of anchor_dirs matches.
    best_match_len = 0
    best_image_tail_start = 0

    for img_start in range(len(image_dirs_lower)):
        match_len = 0
        ai, ii = 0, img_start
        while ai < len(anchor_dirs_lower) and ii < len(image_dirs_lower):
            if anchor_dirs_lower[ai] == image_dirs_lower[ii]:
                match_len += 1
                ai += 1
                ii += 1
            else:
                break
        if match_len > best_match_len:
            best_match_len = match_len
            best_image_tail_start = img_start + match_len

    if best_match_len == 0:
        return None

    # Anchor prefix: root + the first *best_match_len* directory components from anchor.
    anchor_prefix = [anchor_parts[0]] + anchor_dirs_orig[:best_match_len]

    # Image tail: the directory components after the match, plus the filename.
    image_tail = image_dirs_orig[best_image_tail_start:] + [image_filename]

    if not image_tail:
        return None

    return str(Path(*anchor_prefix, *image_tail))


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
        original_image_path = ImageFullPath  # preserve original case for re-root fallback

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

        # Last-resort fallback: re-root the image path onto each search directory by
        # matching common ancestor directory names between the search dir and the
        # recorded image path.  This handles data that has been moved to a different
        # drive or base directory while preserving the internal folder structure.
        if os.path.isabs(original_image_path):
            for search_dir in listAltDirs:
                candidate = _try_rerooted_path(search_dir, original_image_path)
                if candidate is not None and os.path.exists(candidate):
                    return candidate

    return None
