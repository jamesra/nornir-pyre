"""Tests for Pyre startup with no STOS/images loaded."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from pyre.controllers.transformcontroller import TransformController
from pyre.settings.app import AppSettings
from pyre.state import (
    InitializeStateFromSettings,
    StosState,
    _clear_stale_stos_restore_settings,
    get_current_stos_config,
    set_current_stos_config,
)
from pyre.state.managers.image_manager import ImageManager
from pyre.state.managers.image_viewmodel_manager import ImageViewModelManager
from pyre.stos_registration import try_resolve_warped_and_fixed_image_data


class TestTryResolveWarpedAndFixed(unittest.TestCase):
    def test_returns_none_when_image_manager_empty(self) -> None:
        manager = ImageManager()
        self.assertIsNone(
            try_resolve_warped_and_fixed_image_data(
                manager,
                "Source",
                "Target",
            )
        )


class TestInitializeStateFromSettingsEmpty(unittest.TestCase):
    def setUp(self) -> None:
        self.image_manager = ImageManager()
        self.image_viewmodel_manager = ImageViewModelManager()
        self.transform_controller = TransformController()
        self.image_loader = MagicMock()
        self.image_loader._image_manager = self.image_manager
        self.settings = AppSettings()

        set_current_stos_config(StosState(
            transform_controller=self.transform_controller,
            image_manager=self.image_manager,
            image_viewmodel_manager=self.image_viewmodel_manager,
            image_loader=self.image_loader,
            window_manager=None,
        ))

    def tearDown(self) -> None:
        set_current_stos_config(None)

    def test_empty_settings_does_not_raise(self) -> None:
        InitializeStateFromSettings(
            self.transform_controller,
            image_loader=self.image_loader,
            settings=self.settings,
        )
        config = get_current_stos_config()
        assert config is not None
        self.assertIsNone(config._warped_image_permutations)
        self.assertIsNone(config._fixed_image_permutations)

    def test_clear_stale_stos_restore_settings(self) -> None:
        self.settings.stos.stos_filename = "/missing/file.stos"
        self.settings.stos.stos_dirname = "/missing"
        self.settings.stos.source_image = None
        self.settings.stos.target_image = None

        _clear_stale_stos_restore_settings(self.settings)

        self.assertIsNone(self.settings.stos.stos_filename)
        self.assertIsNone(self.settings.stos.stos_dirname)

    def test_missing_stos_clears_settings_and_raises(self) -> None:
        self.settings.stos.stos_filename = "/no/such/file.stos"
        self.image_loader.load_stos.side_effect = FileNotFoundError("missing")

        with self.assertRaises(FileNotFoundError):
            InitializeStateFromSettings(
                self.transform_controller,
                image_loader=self.image_loader,
                settings=self.settings,
            )

        self.assertIsNone(self.settings.stos.stos_filename)


if __name__ == "__main__":
    unittest.main()
