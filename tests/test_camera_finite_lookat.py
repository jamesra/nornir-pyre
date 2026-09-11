"""Camera must reject non-finite lookat/scale so bad transforms cannot rocket the view."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import numpy as np
from nornir_imageregistration.transforms.meshwithrbffallback import MeshWithRBFFallback

from pyre.controllers.transformcontroller import TransformController
from pyre.space import Space
from pyre.ui.camera import Camera
from pyre.views.composite_display import (
    apply_composite_display_pan_delta,
    camera_lookat_from_target_space,
    display_lookat_for_composite,
    lookat_from_display_position,
    rebase_composite_camera_to_display,
)


def _settings() -> MagicMock:
    settings = MagicMock()
    settings.ui.zoom_limits.max = 100.0
    settings.ui.zoom_limits.min = 0.01
    return settings


def _tiny_mesh() -> MeshWithRBFFallback:
    points = np.array([
        [0.0, 0.0, 100.0, 100.0],
        [0.0, 100.0, 100.0, 200.0],
        [100.0, 0.0, 200.0, 100.0],
        [100.0, 100.0, 200.0, 200.0],
    ], dtype=np.float32)
    return MeshWithRBFFallback(points)


class TestCameraRejectsNonFiniteLookat(unittest.TestCase):
    def setUp(self) -> None:
        self.camera = Camera((50.0, 60.0), scale=1.0, settings=_settings())

    def test_lookat_setter_keeps_previous_on_nan(self) -> None:
        before = self.camera.lookat.copy()
        self.camera.lookat = (np.nan, np.nan)
        np.testing.assert_allclose(self.camera.lookat, before)

    def test_lookat_setter_keeps_previous_on_inf(self) -> None:
        before = self.camera.lookat.copy()
        self.camera.lookat = (np.inf, 1.0)
        np.testing.assert_allclose(self.camera.lookat, before)

    def test_lookat_setter_accepts_finite(self) -> None:
        self.camera.lookat = (10.0, 20.0)
        np.testing.assert_allclose(self.camera.lookat, (10.0, 20.0))

    def test_translate_ignores_non_finite_delta(self) -> None:
        before = self.camera.lookat.copy()
        self.camera.translate((np.nan, 5.0))
        np.testing.assert_allclose(self.camera.lookat, before)

    def test_scale_ignores_non_finite(self) -> None:
        self.camera.scale = 2.0
        self.camera.scale = float('nan')
        self.assertEqual(self.camera.scale, 2.0)

    def test_init_with_nan_position_falls_back_to_origin(self) -> None:
        cam = Camera((np.nan, np.nan), settings=_settings())
        np.testing.assert_allclose(cam.lookat, (0.0, 0.0))


class TestCompositeLookatSurvivesNanInverse(unittest.TestCase):
    """When InverseTransform yields NaN, composite helpers must not poison the camera."""

    def setUp(self) -> None:
        self.controller = TransformController(_tiny_mesh())
        self.camera = Camera((150.0, 150.0), scale=1.0, settings=_settings())

    def test_rebase_skips_non_finite_inverse(self) -> None:
        before = self.camera.lookat.copy()
        with patch.object(
                self.controller, 'InverseTransform',
                return_value=np.array([[np.nan, np.nan]], dtype=np.float64)):
            rebase_composite_camera_to_display(
                self.camera, self.controller, np.array([50.0, 50.0]))
        np.testing.assert_allclose(self.camera.lookat, before)

    def test_pan_skips_non_finite_inverse(self) -> None:
        before = self.camera.lookat.copy()
        with patch.object(
                self.controller, 'InverseTransform',
                return_value=np.array([[np.nan, np.nan]], dtype=np.float64)):
            apply_composite_display_pan_delta(
                self.camera, self.controller, np.array([10.0, -5.0]))
        np.testing.assert_allclose(self.camera.lookat, before)

    def test_display_lookat_falls_back_when_forward_is_nan(self) -> None:
        with patch.object(
                self.controller, 'Transform',
                return_value=np.array([[np.nan, np.nan]], dtype=np.float64)):
            display = display_lookat_for_composite(self.camera, self.controller)
        self.assertTrue(np.all(np.isfinite(display)))
        np.testing.assert_allclose(display, self.camera.lookat)

    def test_camera_lookat_from_target_falls_back_to_target_on_nan(self) -> None:
        target = np.array([40.0, 50.0], dtype=np.float64)
        with patch.object(
                self.controller, 'InverseTransform',
                return_value=np.array([[np.nan, np.nan]], dtype=np.float64)):
            mapped = camera_lookat_from_target_space(
                self.controller, target, Space.Source)
        np.testing.assert_allclose(mapped, target)
        self.assertTrue(np.all(np.isfinite(mapped)))

    def test_lookat_from_display_reports_nan_without_assigning(self) -> None:
        with patch.object(
                self.controller, 'InverseTransform',
                return_value=np.array([[np.nan, np.nan]], dtype=np.float64)):
            result = lookat_from_display_position(
                self.controller, np.array([1.0, 2.0]))
        self.assertFalse(np.all(np.isfinite(result)))

    def test_pan_skips_astronomical_inverse(self) -> None:
        before = self.camera.lookat.copy()
        with patch.object(
                self.controller, 'InverseTransform',
                return_value=np.array([[1.14e8, 1.39e8]], dtype=np.float64)):
            apply_composite_display_pan_delta(
                self.camera, self.controller, np.array([10.0, -5.0]))
        np.testing.assert_allclose(self.camera.lookat, before)

    def test_display_lookat_falls_back_when_forward_is_astronomical(self) -> None:
        with patch.object(
                self.controller, 'Transform',
                return_value=np.array([[2.3e9, 2.9e9]], dtype=np.float64)):
            display = display_lookat_for_composite(self.camera, self.controller)
        self.assertTrue(np.all(np.isfinite(display)))
        self.assertLess(float(np.max(np.abs(display))), 1e6)
        np.testing.assert_allclose(display, self.camera.lookat)

    def test_camera_lookat_from_target_falls_back_on_astronomical_inverse(self) -> None:
        target = np.array([40.0, 50.0], dtype=np.float64)
        with patch.object(
                self.controller, 'InverseTransform',
                return_value=np.array([[1.14e8, 1.39e8]], dtype=np.float64)):
            mapped = camera_lookat_from_target_space(
                self.controller, target, Space.Source)
        np.testing.assert_allclose(mapped, target)


if __name__ == '__main__':
    unittest.main()
