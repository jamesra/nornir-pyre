"""STOS group / Manual override path helpers (matches Nornir buildmanager layout)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import os
import re

MANUAL_SUBDIR = "Manual"

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


def ensure_manual_directory(stos_group_folder: str) -> str:
    """Create ``{stos_group_folder}/Manual`` if needed and return its path."""
    manual_dir = manual_directory(stos_group_folder)
    os.makedirs(manual_dir, exist_ok=True)
    return manual_dir


def path_to_manual_transform(stos_group_folder: str, basename: str) -> str | None:
    """Return the manual override path when the file exists (buildmanager-compatible)."""
    manual_path = os.path.join(manual_directory(stos_group_folder), basename)
    return manual_path if os.path.isfile(manual_path) else None


def resolve_default_load_path(auto_path: str | None, manual_path: str | None) -> str | None:
    """Prefer the manual override when present."""
    if manual_path and os.path.isfile(manual_path):
        return manual_path
    return auto_path


def resolve_load_path(
        auto_path: str | None,
        manual_path: str | None,
        source: StosFileSource,
) -> str | None:
    """Return the STOS path for *source* when the backing file exists."""
    if source == StosFileSource.auto:
        return resolve_default_load_path(auto_path, manual_path)
    if source == StosFileSource.original:
        if auto_path and os.path.isfile(auto_path):
            return auto_path
        return None
    if source == StosFileSource.manual:
        if manual_path and os.path.isfile(manual_path):
            return manual_path
        return None
    return None


def resolve_stos_path_in_group(
        stos_group_folder: str,
        basename: str,
        source: StosFileSource,
        *,
        flat_manual: bool = False,
) -> str | None:
    """Resolve auto/manual paths for *basename* under a browser folder."""
    if flat_manual:
        manual_path = os.path.join(stos_group_folder, basename)
        manual_path = manual_path if os.path.isfile(manual_path) else None
        return resolve_load_path(None, manual_path, source)

    auto_path = os.path.join(stos_group_folder, basename)
    auto_path = auto_path if os.path.isfile(auto_path) else None
    manual_path = path_to_manual_transform(stos_group_folder, basename)
    return resolve_load_path(auto_path, manual_path, source)


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
    """One logical row in the Stos Directory listing."""

    basename: str
    auto_path: str | None
    manual_path: str | None
    # quality_score: float | None = None  # Future: sortable quality column

    @property
    def has_manual_override(self) -> bool:
        return self.manual_path is not None and os.path.isfile(self.manual_path)

    @property
    def is_manual_only(self) -> bool:
        """True when a manual override exists and no automatic file is present."""
        has_manual = self.manual_path is not None and os.path.isfile(self.manual_path)
        has_auto = self.auto_path is not None and os.path.isfile(self.auto_path)
        return has_manual and not has_auto

    @property
    def default_load_path(self) -> str | None:
        return resolve_default_load_path(self.auto_path, self.manual_path)

    def load_path_for_source(self, source: StosFileSource) -> str | None:
        """Return the path to load for *source*."""
        return resolve_load_path(self.auto_path, self.manual_path, source)

    @property
    def sort_key(self) -> tuple:
        return _basename_sort_key(self.basename)


def _list_stos_files(folder: str) -> list[str]:
    if not os.path.isdir(folder):
        return []
    return [
        os.path.join(folder, name)
        for name in os.listdir(folder)
        if name.lower().endswith(".stos")
        and os.path.isfile(os.path.join(folder, name))
    ]


def scan_stos_browser_rows(folder: str, mode: BrowseMode = BrowseMode.stos_group) -> list[StosBrowserRow]:
    """Build browser rows for *folder* according to *mode*."""
    if mode == BrowseMode.flat_manual:
        rows = [
            StosBrowserRow(basename=os.path.basename(path), auto_path=None, manual_path=path)
            for path in _list_stos_files(folder)
        ]
    else:
        by_name: dict[str, StosBrowserRow] = {}
        for path in _list_stos_files(folder):
            name = os.path.basename(path)
            row = by_name.get(name)
            if row is None:
                by_name[name] = StosBrowserRow(basename=name, auto_path=path, manual_path=None)
            else:
                by_name[name] = StosBrowserRow(
                    basename=name, auto_path=path, manual_path=row.manual_path)

        manual_folder = manual_directory(folder)
        if os.path.isdir(manual_folder):
            for path in _list_stos_files(manual_folder):
                name = os.path.basename(path)
                row = by_name.get(name)
                if row is None:
                    by_name[name] = StosBrowserRow(basename=name, auto_path=None, manual_path=path)
                else:
                    by_name[name] = StosBrowserRow(
                        basename=name, auto_path=row.auto_path, manual_path=path)

        rows = list(by_name.values())

    rows.sort(key=lambda row: row.sort_key)
    return rows
