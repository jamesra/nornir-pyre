"""Tests for Pyre RotateTranslateWarpedImage method selection and CS2D normalization."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import nornir_imageregistration
from nornir_imageregistration.settings import SliceToSliceMethod, StosBruteSettings

from pyre.common import RotateTranslateWarpedImage


class _MinimalImageManager(dict):
    """Minimal mapping used in place of Pyre's ImageManager."""

    def __contains__(self, key: object) -> bool:
        return super().__contains__(str(key))

    def __getitem__(self, key: object):
        return super().__getitem__(str(key))


class TestRotateTranslateWarpedImage(unittest.TestCase):
    """Rotate-translate helper passes method through and upgrades rigid results."""

    def setUp(self) -> None:
        self._image_manager = _MinimalImageManager()
        self._image_manager["Source"] = MagicMock(shape=(64, 64))
        self._image_manager["Target"] = MagicMock(shape=(64, 64))
        self._app_settings = MagicMock()
        self._app_settings.stos.stos_filename = None
        self._app_settings.stos.source_image = None
        self._app_settings.stos.target_image = None

    @patch("pyre.common.stos.SliceToSliceRigidRegistrationWithPreprocessedImages")
    @patch("pyre.common.resolve_source_and_target_image_data")
    def test_brute_force_method_is_passed_to_registration(
            self,
            mock_resolve: MagicMock,
            mock_register: MagicMock,
    ) -> None:
        """Explicit method overrides default settings (brute vs log polar)."""
        mock_resolve.return_value = (
            self._image_manager["Source"],
            self._image_manager["Target"],
        )
        rigid = nornir_imageregistration.transforms.Rigid(
            target_offset=(1.0, 2.0),
            source_rotation_center=(0.0, 0.0),
            angle=3.0,
        )
        align_record = MagicMock()
        align_record.ToImageTransform.return_value = rigid
        mock_register.return_value = align_record

        settings = StosBruteSettings(method=SliceToSliceMethod.LogPolar)
        result = RotateTranslateWarpedImage(
            source_image_key="Source",
            target_image_key="Target",
            settings=settings,
            method=SliceToSliceMethod.BruteForce,
            image_manager=self._image_manager,
            app_settings=self._app_settings,
        )

        registration_settings = mock_register.call_args.kwargs["settings"]
        self.assertEqual(registration_settings.method, SliceToSliceMethod.BruteForce)
        self.assertIsInstance(
            result, nornir_imageregistration.transforms.CenteredSimilarity2DTransform)
        self.assertAlmostEqual(result.scalar, 1.0)
