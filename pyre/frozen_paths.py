"""Filesystem paths for frozen (PyInstaller) vs development Pyre installs."""

from __future__ import annotations

import os
import sys


def is_frozen() -> bool:
    """Return True when running from a PyInstaller bundle."""
    return bool(getattr(sys, "frozen", False))


def user_data_dir() -> str:
    """Return the per-user writable Pyre configuration directory."""
    appdata = os.environ.get("APPDATA")
    if appdata:
        return os.path.join(appdata, "Nornir", "Pyre")
    return os.path.join(os.path.expanduser("~"), ".nornir", "pyre")


def user_settings_path() -> str:
    """Return the path to the user-writable settings.json file."""
    return os.path.join(user_data_dir(), "settings.json")


def default_log_root() -> str:
    """Return the default NORNIR_LOG_ROOT for installed (frozen) builds."""
    localappdata = os.environ.get("LOCALAPPDATA")
    if localappdata:
        return os.path.join(localappdata, "Nornir", "Pyre", "logs")
    return os.path.join(user_data_dir(), "logs")


def configure_frozen_environment() -> None:
    """Apply frozen-build defaults before logging and settings load."""
    if not is_frozen():
        return

    os.makedirs(user_data_dir(), exist_ok=True)

    if not os.environ.get("NORNIR_LOG_ROOT", "").strip():
        log_root = default_log_root()
        os.makedirs(log_root, exist_ok=True)
        os.environ["NORNIR_LOG_ROOT"] = log_root
