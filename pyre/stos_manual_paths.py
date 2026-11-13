"""STOS group / Manual override path helpers (matches Nornir buildmanager layout)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import os
import re
import stat

MANUAL_SUBDIR = "Manual"
AUTOMATIC_SUBDIR = "Automatic"

# Matches the first two integers in a filename (e.g. "0034-0035_grid.stos").
_SECTION_PAIR_RE = re.compile(r"(\d+)\D+(\d+)")


class BrowseMode(Enum):
    """How the Stos Directory window interprets the opened folder."""

    stos_group = "stos_group"
    flat_manual = "flat_manual"


class StosFileSource(str, Enum):
    """Which STOS file variant to load for a browser row."""

    auto = "auto"
    original = "original"
    input = "input"
    manual = "manual"

    @classmethod
    def from_settings_value(cls, value: str | None) -> StosFileSource:
        """Parse a persisted settings value, defaulting to auto."""
        if value is None:
            return cls.auto
        try:
            return cls(value)
        except ValueError:
            return cls.auto


def _basename_sort_key(name: str) -> tuple:
    lowered = name.lower()
    match = _SECTION_PAIR_RE.search(lowered)
    if match:
        return 0, int(match.group(1)), int(match.group(2)), lowered
    return 1, 0, 0, lowered


def is_manual_input_directory(path: str) -> bool:
    """True when *path* is a directory whose basename is ``Manual``."""
    if not path or not os.path.isdir(path):
        return False
    return os.path.basename(os.path.normpath(path)).lower() == MANUAL_SUBDIR.lower()


def parent_stos_group_folder(manual_folder: str) -> str | None:
    """Return the parent STOS group folder when *manual_folder* is a Manual directory."""
    if not is_manual_input_directory(manual_folder):
        return None
    parent = os.path.dirname(os.path.normpath(manual_folder))
    return parent if parent and os.path.isdir(parent) else None


def manual_directory(stos_group_folder: str) -> str:
    """Return ``{stos_group_folder}/Manual``."""
    return os.path.join(stos_group_folder, MANUAL_SUBDIR)


def automatic_directory(stos_group_folder: str) -> str:
    """Return ``{stos_group_folder}/Automatic``."""
    return os.path.join(stos_group_folder, AUTOMATIC_SUBDIR)


def ensure_manual_directory(stos_group_folder: str) -> str:
    """Create ``{stos_group_folder}/Manual`` if needed and return its path."""
    manual_dir = manual_directory(stos_group_folder)
    os.makedirs(manual_dir, exist_ok=True)
    return manual_dir


def path_to_manual_transform(stos_group_folder: str, basename: str) -> str | None:
    """Return the manual override path when the file exists (buildmanager-compatible)."""
    manual_path = os.path.join(manual_directory(stos_group_folder), basename)
    return manual_path if os.path.isfile(manual_path) else None


def path_to_input_transform(stos_group_folder: str, basename: str) -> str | None:
    """Return the Automatic/ input transform path when the file exists."""
    input_path = os.path.join(automatic_directory(stos_group_folder), basename)
    return input_path if os.path.isfile(input_path) else None


def resolve_default_load_path(auto_path: str | None, manual_path: str | None) -> str | None:
    """Prefer the manual override when present."""
    if manual_path and os.path.isfile(manual_path):
        return manual_path
    return auto_path


def resolve_load_path(
        auto_path: str | None,
        manual_path: str | None,
        source: StosFileSource,
        *,
        input_path: str | None = None,
) -> str | None:
    """Return the STOS path for *source* when the backing file exists."""
    if source == StosFileSource.auto:
        return resolve_default_load_path(auto_path, manual_path)
    if source == StosFileSource.original:
        if auto_path and os.path.isfile(auto_path):
            return auto_path
        return None
    if source == StosFileSource.input:
        if input_path and os.path.isfile(input_path):
            return input_path
        return None
    if source == StosFileSource.manual:
        if manual_path and os.path.isfile(manual_path):
            return manual_path
        return None
    return None


def expected_stos_path_for_source(
        folder: str,
        basename: str,
        source: StosFileSource,
        *,
        mode: BrowseMode = BrowseMode.stos_group,
) -> str:
    """Return the canonical path for *source* under *folder*, whether or not it exists."""
    if mode == BrowseMode.flat_manual:
        return os.path.join(folder, basename)
    if source == StosFileSource.input:
        return os.path.join(automatic_directory(folder), basename)
    if source == StosFileSource.manual:
        return os.path.join(manual_directory(folder), basename)
    return os.path.join(folder, basename)


def _stat_file(path: str | None) -> tuple[str, float] | None:
    """Return ``(path, mtime)`` when *path* is an existing file, else None (one stat call)."""
    if not path:
        return None
    try:
        info = os.stat(path)
    except OSError:
        return None
    return (path, info.st_mtime) if stat.S_ISREG(info.st_mode) else None


def _first_file(*paths: str | None) -> tuple[str | None, float | None]:
    """Return the path and mtime of the first existing file in *paths*."""
    for path in paths:
        found = _stat_file(path)
        if found is not None:
            return found
    return None, None


def refresh_browser_row(
        folder: str | None,
        row: StosBrowserRow,
        mode: BrowseMode = BrowseMode.stos_group,
) -> StosBrowserRow:
    """Re-stat output / Automatic / Manual files for one *row* (selection, load, context menu).

    Keeps a cached path that still exists so injected test rows remain valid, and
    picks up files created under *folder* after the last directory scan.
    """
    if mode == BrowseMode.flat_manual:
        expected_manual = os.path.join(folder, row.basename) if folder else None
        manual_path, manual_mtime = _first_file(row.manual_path, expected_manual)
        return StosBrowserRow(
            basename=row.basename,
            auto_path=None,
            manual_path=manual_path,
            input_path=None,
            quality_score=row.quality_score,
            manual_mtime=manual_mtime,
        )

    expected_auto = os.path.join(folder, row.basename) if folder else None
    expected_input = (
        os.path.join(automatic_directory(folder), row.basename) if folder else None)
    expected_manual = (
        os.path.join(manual_directory(folder), row.basename) if folder else None)
    auto_path, auto_mtime = _first_file(row.auto_path, expected_auto)
    manual_path, manual_mtime = _first_file(row.manual_path, expected_manual)
    input_path, input_mtime = _first_file(row.input_path, expected_input)
    return StosBrowserRow(
        basename=row.basename,
        auto_path=auto_path,
        manual_path=manual_path,
        input_path=input_path,
        quality_score=row.quality_score,
        auto_mtime=auto_mtime,
        manual_mtime=manual_mtime,
        input_mtime=input_mtime,
    )


def resolve_stos_path_in_group(
        stos_group_folder: str,
        basename: str,
        source: StosFileSource,
        *,
        flat_manual: bool = False,
) -> str | None:
    """Resolve output / Automatic input / Manual paths for *basename* under a browser folder."""
    if flat_manual:
        manual_path = os.path.join(stos_group_folder, basename)
        manual_path = manual_path if os.path.isfile(manual_path) else None
        return resolve_load_path(None, manual_path, source)

    auto_path = os.path.join(stos_group_folder, basename)
    auto_path = auto_path if os.path.isfile(auto_path) else None
    input_path = path_to_input_transform(stos_group_folder, basename)
    manual_path = path_to_manual_transform(stos_group_folder, basename)
    return resolve_load_path(auto_path, manual_path, source, input_path=input_path)


def resolve_stos_restore_path(
        stos_filename: str,
        *,
        stos_group_folder: str | None,
        stos_browser_basename: str | None,
        stos_file_source: str | None,
        flat_manual: bool,
) -> str:
    """Re-resolve a saved STOS path using browser context and file-source preference."""
    if not stos_group_folder or not os.path.isdir(stos_group_folder):
        return stos_filename

    basename = stos_browser_basename or os.path.basename(stos_filename)
    source = StosFileSource.from_settings_value(stos_file_source)
    resolved = resolve_stos_path_in_group(
        stos_group_folder,
        basename,
        source,
        flat_manual=flat_manual,
    )
    return resolved if resolved is not None else stos_filename


@dataclass(frozen=True)
class StosBrowserRow:
    """One logical row in the Stos Directory listing.

    A path is set only when that file existed when the row was built (folder scan or
    :func:`refresh_browser_row`), and its mtime comes from the same listing or stat.
    The properties below never touch the file system: on an SMB share each stat took
    ~240 ms, and the table refresh called them for every row on the UI thread.
    """

    basename: str
    auto_path: str | None
    manual_path: str | None
    input_path: str | None = None
    quality_score: float | None = None
    auto_mtime: float | None = None
    manual_mtime: float | None = None
    input_mtime: float | None = None

    @property
    def has_manual_override(self) -> bool:
        return self.manual_path is not None

    @property
    def has_input_transform(self) -> bool:
        """True when ``Automatic/<basename>`` exists for this row."""
        return self.input_path is not None

    @property
    def is_manual_only(self) -> bool:
        """True when a manual override exists and no automatic file is present."""
        return self.manual_path is not None and self.auto_path is None

    @property
    def default_load_path(self) -> str | None:
        """Prefer the manual override when present."""
        return self.manual_path or self.auto_path

    def load_path_for_source(self, source: StosFileSource) -> str | None:
        """Return the path to load for *source*, or None when that file is absent."""
        if source == StosFileSource.auto:
            return self.default_load_path
        if source == StosFileSource.original:
            return self.auto_path
        if source == StosFileSource.input:
            return self.input_path
        if source == StosFileSource.manual:
            return self.manual_path
        return None

    def mtime_for_path(self, path: str | None) -> float | None:
        """Return the recorded mtime of *path* when it is one of this row's files."""
        if path is None:
            return None
        if path == self.manual_path:
            return self.manual_mtime
        if path == self.auto_path:
            return self.auto_mtime
        if path == self.input_path:
            return self.input_mtime
        return None

    def with_quality_score(self, score: float | None) -> StosBrowserRow:
        """Return a copy of this row with *score* attached."""
        return replace(self, quality_score=score)

    @property
    def sort_key(self) -> tuple:
        return _basename_sort_key(self.basename)


def _list_stos_files(folder: str) -> list[tuple[str, float]]:
    """Return ``(path, mtime)`` for each ``*.stos`` file in *folder*, from one directory listing.

    On Windows ``DirEntry.is_file()`` and ``DirEntry.stat()`` use data the listing already
    returned, so this costs no per-file network round trip on a share.
    """
    try:
        with os.scandir(folder) as entries:
            return [
                (entry.path, entry.stat().st_mtime)
                for entry in entries
                if entry.name.lower().endswith(".stos") and entry.is_file()
            ]
    except OSError:
        return []


def _upsert_browser_row(
        by_name: dict[str, StosBrowserRow],
        basename: str,
        *,
        auto: tuple[str, float] | None = None,
        input_file: tuple[str, float] | None = None,
        manual: tuple[str, float] | None = None,
) -> None:
    """Merge one listed STOS ``(path, mtime)`` into *by_name*, preserving the other variants."""
    row = by_name.get(basename) or StosBrowserRow(basename=basename, auto_path=None, manual_path=None)
    if auto is not None:
        row = replace(row, auto_path=auto[0], auto_mtime=auto[1])
    if input_file is not None:
        row = replace(row, input_path=input_file[0], input_mtime=input_file[1])
    if manual is not None:
        row = replace(row, manual_path=manual[0], manual_mtime=manual[1])
    by_name[basename] = row


def scan_stos_browser_rows(folder: str, mode: BrowseMode = BrowseMode.stos_group) -> list[StosBrowserRow]:
    """Build browser rows for *folder* according to *mode*.

    Lists the folder, ``Automatic/`` and ``Manual/`` once each; rows carry existence and
    mtimes from those listings. Slow on a large share folder, so call it off the UI thread.
    """
    if mode == BrowseMode.flat_manual:
        rows = [
            StosBrowserRow(basename=os.path.basename(path), auto_path=None, manual_path=path,
                           manual_mtime=mtime)
            for path, mtime in _list_stos_files(folder)
        ]
    else:
        by_name: dict[str, StosBrowserRow] = {}
        for listed in _list_stos_files(folder):
            _upsert_browser_row(by_name, os.path.basename(listed[0]), auto=listed)
        for listed in _list_stos_files(automatic_directory(folder)):
            _upsert_browser_row(by_name, os.path.basename(listed[0]), input_file=listed)
        for listed in _list_stos_files(manual_directory(folder)):
            _upsert_browser_row(by_name, os.path.basename(listed[0]), manual=listed)
        rows = list(by_name.values())

    rows.sort(key=lambda row: row.sort_key)
    return rows


VOLUME_DATA_FILENAME = "VolumeData.xml"


@dataclass(frozen=True)
class StosVolumeMismatch:
    """Images of a STOS being saved that live in a different volume than its destination."""

    destination_volume_root: str
    # (image path, that image's volume root) for each image outside the destination volume.
    mismatched_images: tuple[tuple[str, str], ...]


def _normalized_path(path: str) -> str:
    return os.path.normcase(os.path.abspath(path))


def find_volume_root(file_path: str) -> str | None:
    """Return the nearest ancestor directory of *file_path* holding ``VolumeData.xml``.

    The search starts at the directory containing *file_path* (which need not exist yet,
    e.g. a save destination) and walks up to the filesystem root. Returns the normalized
    directory path, or None when no ancestor is a Nornir volume.
    """
    if not file_path:
        return None
    directory = os.path.dirname(_normalized_path(file_path))
    while True:
        if os.path.isfile(os.path.join(directory, VOLUME_DATA_FILENAME)):
            return directory
        parent = os.path.dirname(directory)
        if parent == directory:
            return None
        directory = parent


def stos_volume_mismatch(
        destination_path: str,
        image_paths: list[str | None],
) -> StosVolumeMismatch | None:
    """Report images in *image_paths* whose volume differs from *destination_path*'s volume.

    Returns None when everything matches, when the destination is not inside a volume, or
    when an image is not inside a volume (those images are not compared).
    """
    destination_root = find_volume_root(destination_path)
    if destination_root is None:
        return None
    mismatched: list[tuple[str, str]] = []
    for image_path in image_paths:
        if not image_path:
            continue
        image_root = find_volume_root(image_path)
        if image_root is not None and image_root != destination_root:
            mismatched.append((image_path, image_root))
    if not mismatched:
        return None
    return StosVolumeMismatch(destination_root, tuple(mismatched))
