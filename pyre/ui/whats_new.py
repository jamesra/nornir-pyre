"""Show the What's New dialog and remember which package version was shown."""

from __future__ import annotations

import logging

from PyQt6.QtWidgets import QWidget

from pyre.settings.app import AppSettings
from pyre.settings.persistence import save_app_settings
from pyre.ui.windows.whats_new_dialog import WhatsNewDialog
from pyre.user_changelog import (
    markdown_for_versions,
    package_version,
    parse_changelog_sections,
    read_changelog_text,
    versions_newer_than,
    whats_new_markdown,
)

logger = logging.getLogger(__name__)


def _remember_shown(settings: AppSettings, current: str) -> None:
    if settings.last_shown_changelog_version == current:
        return
    settings.last_shown_changelog_version = current
    try:
        save_app_settings(settings)
    except Exception:
        logger.debug("Could not save last_shown_changelog_version", exc_info=True)


def show_whats_new(
        parent: QWidget | None,
        settings: AppSettings,
        *,
        full_history: bool = False,
) -> bool:
    """Show What's New. Returns True when a dialog was shown.

    *full_history* (Help menu) shows notes for the installed version and older.
    Startup uses *full_history* False and only shows sections newer than
    ``settings.last_shown_changelog_version``; after dismiss, that field is
    set to the installed package version.
    """
    current = package_version()
    if full_history:
        markdown = whats_new_markdown(
            last_shown=None, current=current, full_history=True)
        if not markdown.strip():
            markdown = "No user changelog was found in this Pyre install."
        WhatsNewDialog(parent, markdown).exec()
        _remember_shown(settings, current)
        return True

    text = read_changelog_text()
    sections = parse_changelog_sections(text)
    versions = versions_newer_than(
        sections,
        last_shown=settings.last_shown_changelog_version,
        current=current,
    )
    if not versions:
        _remember_shown(settings, current)
        return False

    markdown = markdown_for_versions(sections, versions)
    WhatsNewDialog(parent, markdown).exec()
    _remember_shown(settings, current)
    return True


def maybe_show_whats_new_after_upgrade(
        parent: QWidget | None,
        settings: AppSettings,
) -> bool:
    """Show What's New once after install/upgrade when there are new notes."""
    return show_whats_new(parent, settings, full_history=False)
