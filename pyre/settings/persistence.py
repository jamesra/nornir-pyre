"""Where AppSettings live on disk and how they are written."""

from __future__ import annotations

import logging
import os

from pyre.frozen_paths import is_frozen, user_settings_path
from pyre.settings.app import AppSettings

logger = logging.getLogger(__name__)


def settings_output_path() -> str:
    """Path of the settings JSON: the user profile when frozen, else ``pyre/settings.json``."""
    if is_frozen():
        settings_path = user_settings_path()
        os.makedirs(os.path.dirname(settings_path), exist_ok=True)
        return settings_path
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'settings.json')


def save_app_settings(settings: AppSettings) -> str:
    """Write ``settings`` to disk and return the path.

    Called at exit and whenever a settings dialog is accepted, so a debugger stop or
    crash between edits and shutdown does not lose the change.
    """
    output_file = settings_output_path()
    with open(output_file, 'w') as file:
        file.write(settings.model_dump_json(indent=4))
    logger.info("Saved settings to %s", output_file)
    return output_file
