"""Tests for host shared-memory staging of control-point alignment payloads."""

from __future__ import annotations

import pickle
import unittest

import numpy as np

import nornir_imageregistration
from nornir_imageregistration.computational_lib import HasCupy
from nornir_imageregistration.image_permutation_helper import ImagePermutationHelper
from pyre.controllers.alignment_payload import (
    SharedImagePairRef,
    stage_image_pair,
)


def _helper(size: int = 32, *, use_cupy: bool = False) -> ImagePermutationHelper:
    rng = np.random.default_rng(1)
    image = rng.random((size, size), dtype=np.float32)
    mask = np.ones((size, size), dtype=bool)
    if use_cupy:
        import cupy as cp

        return ImagePermutationHelper(cp.asarray(image), cp.asarray(mask))
    return ImagePermutationHelper(image, mask)


class TestStageImagePair(unittest.TestCase):
    def test_round_trip_matches_source_arrays(self) -> None:
        source = _helper()
        target = _helper(48)
        staged = stage_image_pair(source, target)
        self.assertIsNotNone(staged)
        assert staged is not None
        try:
            with staged.ref.source.attach() as (pixels, mask, stats):
                np.testing.assert_allclose(
                    pixels, np.asarray(source.ImageWithMaskAsNoise))
                np.testing.assert_array_equal(mask, np.asarray(source.BlendedMask))
                self.assertAlmostEqual(stats.median, float(source.Stats.median))
                self.assertAlmostEqual(stats.std, float(source.Stats.std))
            with staged.ref.target.attach() as (pixels, _mask, _stats):
                self.assertEqual(pixels.shape, (48, 48))
        finally:
            staged.close()

    def test_ref_is_picklable_and_small(self) -> None:
        """Only segment names cross the pipe, so the payload must not carry pixels."""
        staged = stage_image_pair(_helper(256), _helper(256))
        assert staged is not None
        try:
            blob = pickle.dumps(staged.ref)
            self.assertIsInstance(pickle.loads(blob), SharedImagePairRef)
            self.assertLess(len(blob), 2048)
        finally:
            staged.close()

    def test_attached_view_is_read_only(self) -> None:
        staged = stage_image_pair(_helper(), _helper())
        assert staged is not None
        try:
            with staged.ref.source.attach() as (pixels, _mask, _stats):
                with self.assertRaises(ValueError):
                    pixels[0, 0] = 1.0
        finally:
            staged.close()

    def test_matches_only_the_staged_helpers(self) -> None:
        source = _helper()
        target = _helper()
        staged = stage_image_pair(source, target)
        assert staged is not None
        try:
            self.assertTrue(staged.matches(source, target))
            self.assertFalse(staged.matches(target, source))
            self.assertFalse(staged.matches(source, _helper()))
        finally:
            staged.close()

    def test_close_is_idempotent_and_stops_matching(self) -> None:
        source = _helper()
        target = _helper()
        staged = stage_image_pair(source, target)
        assert staged is not None
        staged.close()
        staged.close()
        self.assertFalse(staged.matches(source, target))

    def test_empty_image_does_not_stage(self) -> None:
        source = _helper()
        broken = _helper()
        broken._image_with_mask_as_noise = np.zeros((0, 0), dtype=np.float32)
        self.assertIsNone(stage_image_pair(broken, source))

    @unittest.skipUnless(HasCupy(), "requires CuPy")
    def test_cupy_helper_stages_to_host(self) -> None:
        """A CuPy session must still reach a worker as host memory."""
        source = _helper(use_cupy=True)
        staged = stage_image_pair(source, _helper(use_cupy=True))
        self.assertIsNotNone(staged)
        assert staged is not None
        try:
            with staged.ref.source.attach() as (pixels, mask, _stats):
                self.assertIsInstance(pixels, np.ndarray)
                self.assertIsInstance(mask, np.ndarray)
                np.testing.assert_allclose(
                    pixels,
                    nornir_imageregistration.EnsureNumpyArray(
                        source.ImageWithMaskAsNoise))
        finally:
            staged.close()


if __name__ == "__main__":
    unittest.main()
