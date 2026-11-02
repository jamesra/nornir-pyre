"""Load and filter the curated Pyre user changelog for What's New."""

from __future__ import annotations

import logging
import os
import re

logger = logging.getLogger(__name__)

# "## 1.8.4" or "## 1.8.4 — 2026-11-01" / "— not yet released" (em dash, en dash, or hyphen).
_VERSION_HEADING = re.compile(
    r"^##\s+(\d+\.\d+\.\d+)(?:\s+[—–-]\s+(.+?))?\s*$",
    re.MULTILINE,
)
_CHANGELOG_NAME = "CHANGELOG.user.md"


def package_version() -> str:
    """Installed ``pyre`` package version, or ``0.0.0`` when metadata is missing."""
    try:
        from importlib.metadata import version as _pkg_version
        return _pkg_version("pyre")
    except Exception:
        return "0.0.0"


def changelog_path() -> str | None:
    """Return the path to CHANGELOG.user.md inside the package, if present."""
    import pyre
    path = os.path.join(pyre.__path__[0], _CHANGELOG_NAME)
    if os.path.isfile(path):
        return path
    return None


def read_changelog_text() -> str:
    """Return the raw user changelog markdown, or a short missing-file message."""
    path = changelog_path()
    if path is None:
        return "No user changelog was found in this Pyre install."
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def parse_changelog_sections(text: str) -> dict[str, str]:
    """Map ``X.Y.Z`` → section body (markdown without the ``##`` heading)."""
    return {version: body for version, _label, body in parse_changelog_entries(text)}


def parse_changelog_entries(text: str) -> list[tuple[str, str | None, str]]:
    """Return ``(version, release_label, body)`` newest-first as written in the file.

    *release_label* is the text after the em dash (date or ``not yet released``), or
    ``None`` when the heading is bare ``## X.Y.Z``.
    """
    matches = list(_VERSION_HEADING.finditer(text))
    entries: list[tuple[str, str | None, str]] = []
    for index, match in enumerate(matches):
        version = match.group(1)
        label = match.group(2)
        if label is not None:
            label = label.strip() or None
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        entries.append((version, label, text[start:end].strip()))
    return entries


def _version_tuple(version: str) -> tuple[int, ...]:
    parts = version.split(".")
    out: list[int] = []
    for part in parts:
        try:
            out.append(int(part))
        except ValueError:
            out.append(0)
    return tuple(out)


def version_greater(a: str, b: str) -> bool:
    """True when *a* is a newer X.Y.Z than *b*."""
    return _version_tuple(a) > _version_tuple(b)


def version_less_or_equal(a: str, b: str) -> bool:
    """True when *a* <= *b* as X.Y.Z."""
    return _version_tuple(a) <= _version_tuple(b)


def versions_newer_than(
        sections: dict[str, str],
        *,
        last_shown: str | None,
        current: str,
) -> list[str]:
    """Versions to show after an upgrade, newest first.

    When *last_shown* is None (first run of this feature, or a fresh profile),
    only the *current* package version section is returned so upgrades from
    older Pyre still get one focused dialog rather than the full history.
    """
    if last_shown is None:
        return [current] if current in sections else []

    chosen = [
        version
        for version in sections
        if version_greater(version, last_shown) and version_less_or_equal(version, current)
    ]
    return sorted(chosen, key=_version_tuple, reverse=True)


def markdown_for_versions(
        sections: dict[str, str],
        versions: list[str],
        *,
        release_labels: dict[str, str | None] | None = None,
) -> str:
    """Build a What's New markdown document for *versions* (already ordered)."""
    if not versions:
        return ""
    labels = release_labels or {}
    blocks: list[str] = ["# What's New in Pyre\n"]
    for version in versions:
        body = sections.get(version, "").strip()
        label = labels.get(version)
        if label:
            blocks.append(f"## Pyre {version} — {label}\n")
        else:
            blocks.append(f"## Pyre {version}\n")
        if body:
            blocks.append(body + "\n")
    return "\n".join(blocks).strip() + "\n"


def whats_new_markdown(
        *,
        last_shown: str | None,
        current: str | None = None,
        full_history: bool = False,
) -> str:
    """Markdown for the What's New dialog.

    *full_history* (Help menu) shows every section at or below *current*.
    Otherwise only sections newer than *last_shown* are included.
    """
    text = read_changelog_text()
    entries = parse_changelog_entries(text)
    if not entries:
        return text
    sections = {version: body for version, _label, body in entries}
    release_labels = {version: label for version, label, _body in entries}
    installed = current if current is not None else package_version()
    if full_history:
        versions = sorted(
            (v for v in sections if version_less_or_equal(v, installed)),
            key=_version_tuple,
            reverse=True,
        )
    else:
        versions = versions_newer_than(
            sections, last_shown=last_shown, current=installed)
    return markdown_for_versions(
        sections, versions, release_labels=release_labels)
