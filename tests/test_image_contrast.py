"""Unit tests for Source/Target display contrast helpers."""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock

import numpy as np
from PIL import Image
from PIL.PngImagePlugin import PngInfo
from pyre.image_contrast import (
    ContrastedImagePermutationHelper,
    apply_contrast_array,
    auto_contrast,
    contrasted_permutation_helper,
    image_file_is_crushed,
    is_identity_contrast,
    normalize_contrast,
    reset_contrast_for_space,
    set_contrast_for_space,
)
from pyre.settings.app import AppSettings, ImageDisplayContrast
from pyre.space import Space


class TestNormalizeContrast(unittest.TestCase):
    def test_identity_defaults(self) -> None:
        c = normalize_contrast(ImageDisplayContrast())
        self.assertTrue(is_identity_contrast(c))
        self.assertEqual(c.min, 0.0)
        self.assertEqual(c.max, 255.0)
        self.assertEqual(c.gamma, 1.0)

    def test_clamp_levels_and_gamma(self) -> None:
        c = normalize_contrast(ImageDisplayContrast(min=-10, max=400, gamma=100))
        self.assertEqual(c.min, 0.0)
        self.assertEqual(c.max, 255.0)
        self.assertEqual(c.gamma, 10.0)
        c2 = normalize_contrast(ImageDisplayContrast(min=10, max=200, gamma=0.001))
        self.assertEqual(c2.gamma, 0.01)

    def test_nudge_when_min_ge_max_prefer_max(self) -> None:
        c = normalize_contrast(ImageDisplayContrast(min=100, max=100), prefer_max=True)
        self.assertLess(c.min, c.max)
        self.assertAlmostEqual(c.max, 100.0)

    def test_nudge_when_min_ge_max_prefer_min(self) -> None:
        c = normalize_contrast(ImageDisplayContrast(min=100, max=50), prefer_max=False)
        self.assertLess(c.min, c.max)
        self.assertAlmostEqual(c.min, 100.0)


class TestApplyContrastArray(unittest.TestCase):
    def test_identity_returns_same_object(self) -> None:
        image = np.arange(16, dtype=np.float32).reshape(4, 4)
        out = apply_contrast_array(image, ImageDisplayContrast())
        self.assertIs(out, image)

    def test_identity_copy_when_requested(self) -> None:
        image = np.arange(16, dtype=np.float32).reshape(4, 4)
        out = apply_contrast_array(image, ImageDisplayContrast(), copy_on_identity=True)
        self.assertIsNot(out, image)
        np.testing.assert_array_equal(out, image)

    def test_min_max_stretch(self) -> None:
        image = np.array([[0.0, 127.5, 255.0]], dtype=np.float32)
        out = apply_contrast_array(
            image, ImageDisplayContrast(min=0.0, max=255.0, gamma=1.0))
        np.testing.assert_allclose(out, image, rtol=1e-5)

        stretched = apply_contrast_array(
            image, ImageDisplayContrast(min=0.0, max=127.5, gamma=1.0))
        self.assertAlmostEqual(float(stretched[0, 0]), 0.0, places=4)
        self.assertAlmostEqual(float(stretched[0, 1]), 255.0, places=3)
        self.assertAlmostEqual(float(stretched[0, 2]), 255.0, places=3)

    def test_unit_interval_uses_display_levels_and_keeps_01_range(self) -> None:
        """0–1 mosaics must not be zeroed by 0–255 contrast windows."""
        image = np.array([[0.0, 0.5, 1.0]], dtype=np.float32)
        out = apply_contrast_array(
            image, ImageDisplayContrast(min=60.4, max=204.0, gamma=1.0))
        self.assertGreater(float(out.max()), 0.1)
        self.assertLessEqual(float(out.max()), 1.0 + 1e-5)
        self.assertAlmostEqual(float(out[0, 0]), 0.0, places=4)
        expected_mid = (0.5 * 255.0 - 60.4) / (204.0 - 60.4)
        self.assertAlmostEqual(float(out[0, 1]), expected_mid, places=3)

    def test_histogram_spreads_unit_interval_into_display_bins(self) -> None:
        from pyre.image_contrast import approximate_image_histogram

        rng = np.random.default_rng(0)
        image = rng.random((64, 64), dtype=np.float32)
        hist = approximate_image_histogram(image)
        self.assertIsNotNone(hist)
        assert hist is not None
        self.assertGreater(hist.NumSamples, 0)
        occupied = sum(1 for count in hist.Bins if count > 0)
        self.assertGreater(occupied, 5)

    def test_gamma_mid_gray(self) -> None:
        # After normalize to [0,1], mid gray 0.5 with gamma=2 → pow(0.5, 0.5) ≈ 0.707 → ~180.3
        image = np.array([[127.5]], dtype=np.float32)
        out = apply_contrast_array(
            image, ImageDisplayContrast(min=0.0, max=255.0, gamma=2.0))
        self.assertAlmostEqual(float(out[0, 0]), 255.0 * (0.5 ** 0.5), places=2)


class TestSettingsContrastHelpers(unittest.TestCase):
    def test_set_and_reset(self) -> None:
        settings = AppSettings()
        written = set_contrast_for_space(
            Space.Source,
            ImageDisplayContrast(min=20, max=200, gamma=1.5),
            settings,
        )
        self.assertEqual(settings.ui.source_contrast.min, written.min)
        reset = reset_contrast_for_space(Space.Source, settings)
        self.assertTrue(is_identity_contrast(reset))
        self.assertTrue(is_identity_contrast(settings.ui.source_contrast))


class TestContrastedPermutationHelper(unittest.TestCase):
    def test_identity_returns_same_helper(self) -> None:
        helper = MagicMock()
        helper.ImageWithMaskAsNoise = np.ones((2, 2), dtype=np.float32)
        out = contrasted_permutation_helper(helper, ImageDisplayContrast())
        self.assertIs(out, helper)

    def test_non_identity_returns_contrasted_copy(self) -> None:
        helper = MagicMock()
        raw = np.full((4, 4), 64.0, dtype=np.float32)
        helper.ImageWithMaskAsNoise = raw
        helper.Image = raw
        helper.Mask = None
        helper.BlendedMask = np.ones((4, 4), dtype=bool)
        helper.Stats = object()
        helper.shape = (4, 4)

        wrapped = contrasted_permutation_helper(
            helper, ImageDisplayContrast(min=0.0, max=128.0, gamma=1.0))
        self.assertIsInstance(wrapped, ContrastedImagePermutationHelper)
        contrasted = wrapped.ImageWithMaskAsNoise  # type: ignore[union-attr]
        self.assertIsNot(contrasted, raw)
        self.assertAlmostEqual(float(contrasted[0, 0]), 127.5, places=1)


class TestCrushedImageAutoContrast(unittest.TestCase):
    """Quantized (noise-crushed) images load with Auto contrast; other images keep their contrast."""

    def setUp(self) -> None:
        self._dir = tempfile.mkdtemp(prefix='pyre_crush_contrast_')
        rng = np.random.default_rng(0)
        # Crushed codes as in RC1_Crush Quantized ds32 images: 0-60, median ~29.
        self.codes = np.clip(rng.normal(29, 4, (64, 64)), 0, 60).astype(np.uint8)
        self.crushed_path = os.path.join(self._dir, 'crushed.png')
        info = PngInfo()
        info.add_text('nornir_crush', '{"bits": 8, "step": 412, "version": 1}')
        Image.fromarray(self.codes).save(self.crushed_path, pnginfo=info)
        self.plain_path = os.path.join(self._dir, 'plain.png')
        Image.fromarray(self.codes).save(self.plain_path)

    def tearDown(self) -> None:
        shutil.rmtree(self._dir, ignore_errors=True)

    def test_detects_crush_chunk(self) -> None:
        self.assertTrue(image_file_is_crushed(self.crushed_path))
        self.assertFalse(image_file_is_crushed(self.plain_path))
        self.assertFalse(image_file_is_crushed(os.path.join(self._dir, 'missing.png')))
        self.assertFalse(image_file_is_crushed(None))

    def test_auto_contrast_spans_the_codes(self) -> None:
        contrast = auto_contrast(self.codes, gamma=1.5)
        assert contrast is not None
        self.assertGreaterEqual(contrast.min, float(self.codes.min()))
        self.assertLessEqual(contrast.max, float(self.codes.max()) + 1)
        self.assertLess(contrast.max - contrast.min, 60.0)
        self.assertEqual(contrast.gamma, 1.5)

    def test_load_sets_auto_contrast_only_for_crushed_images(self) -> None:
        from pyre.ui.windows.stoswindow import StosWindow

        def result(path: str) -> MagicMock:
            r = MagicMock()
            r.image_fullpath = path
            r.permutations.Image = self.codes
            return r

        settings = AppSettings()
        kept = ImageDisplayContrast(min=10.0, max=200.0, gamma=1.0)
        set_contrast_for_space(Space.Target, kept, settings)
        load_result = MagicMock()
        load_result.source = result(self.crushed_path)
        load_result.target = result(self.plain_path)

        StosWindow.auto_contrast_crushed_images(load_result, settings)

        self.assertEqual(settings.ui.source_contrast, auto_contrast(self.codes))
        self.assertFalse(is_identity_contrast(settings.ui.source_contrast))
        self.assertEqual(settings.ui.target_contrast, kept)


if __name__ == '__main__':
    unittest.main()
