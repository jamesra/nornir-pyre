"""User changelog parsing and What's New version filtering."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from pyre.settings.app import AppSettings
from pyre.user_changelog import (
    markdown_for_versions,
    parse_changelog_sections,
    version_greater,
    versions_newer_than,
    whats_new_markdown,
)


_SAMPLE = """# Pyre user changelog

## 1.8.3

- Fine-tune Spacebar.

## 1.8.2

- Save Warped Image fix.

## 1.7.7

- Cancel on STOS open.
"""


class TestUserChangelogParse(unittest.TestCase):
    def test_parse_sections(self) -> None:
        sections = parse_changelog_sections(_SAMPLE)
        self.assertEqual(set(sections), {"1.8.3", "1.8.2", "1.7.7"})
        self.assertIn("Fine-tune", sections["1.8.3"])

    def test_version_greater(self) -> None:
        self.assertTrue(version_greater("1.8.3", "1.8.2"))
        self.assertFalse(version_greater("1.8.2", "1.8.3"))
        self.assertFalse(version_greater("1.8.2", "1.8.2"))

    def test_first_run_shows_only_current(self) -> None:
        sections = parse_changelog_sections(_SAMPLE)
        self.assertEqual(
            versions_newer_than(sections, last_shown=None, current="1.8.3"),
            ["1.8.3"],
        )

    def test_upgrade_shows_intervening_versions(self) -> None:
        sections = parse_changelog_sections(_SAMPLE)
        self.assertEqual(
            versions_newer_than(sections, last_shown="1.7.7", current="1.8.3"),
            ["1.8.3", "1.8.2"],
        )

    def test_already_shown_current_is_empty(self) -> None:
        sections = parse_changelog_sections(_SAMPLE)
        self.assertEqual(
            versions_newer_than(sections, last_shown="1.8.3", current="1.8.3"),
            [],
        )

    def test_markdown_for_versions(self) -> None:
        sections = parse_changelog_sections(_SAMPLE)
        md = markdown_for_versions(sections, ["1.8.3", "1.8.2"])
        self.assertIn("## Pyre 1.8.3", md)
        self.assertIn("## Pyre 1.8.2", md)
        self.assertNotIn("1.7.7", md)


class TestWhatsNewStartup(unittest.TestCase):
    def test_startup_skips_when_already_seen(self) -> None:
        from pyre.ui.whats_new import maybe_show_whats_new_after_upgrade

        settings = AppSettings(last_shown_changelog_version="1.8.3")
        with patch("pyre.ui.whats_new.package_version", return_value="1.8.3"), \
                patch("pyre.ui.whats_new.WhatsNewDialog") as dialog_cls, \
                patch("pyre.ui.whats_new.read_changelog_text", return_value=_SAMPLE):
            shown = maybe_show_whats_new_after_upgrade(None, settings)
        self.assertFalse(shown)
        dialog_cls.assert_not_called()

    def test_startup_shows_and_remembers(self) -> None:
        from pyre.ui.whats_new import maybe_show_whats_new_after_upgrade

        settings = AppSettings(last_shown_changelog_version="1.8.2")
        with patch("pyre.ui.whats_new.package_version", return_value="1.8.3"), \
                patch("pyre.ui.whats_new.WhatsNewDialog") as dialog_cls, \
                patch("pyre.ui.whats_new.save_app_settings") as save, \
                patch("pyre.ui.whats_new.read_changelog_text", return_value=_SAMPLE):
            dialog_cls.return_value.exec = MagicMock()
            shown = maybe_show_whats_new_after_upgrade(None, settings)
        self.assertTrue(shown)
        dialog_cls.assert_called_once()
        self.assertEqual(settings.last_shown_changelog_version, "1.8.3")
        save.assert_called_once()


if __name__ == "__main__":
    unittest.main()
