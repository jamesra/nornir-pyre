"""Images deeper than 8 bits are held as float32 so they keep their precision."""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest import mock

import numpy as np
from PIL import Image
from pyre.settings.app import AppSettings
from pyre.state.imageloader import ImageLoader
from pyre.viewmodels.imageviewmodel import ImageViewModel, working_float_dtype


def _write_ramp(folder: str, name: str, dtype: type, top: int) -> tuple[str, np.ndarray]:
    """Write a horizontal ramp image of *dtype* reaching *top* and return its path and pixels."""
    pixels = np.round(np.linspace(0, top, 64 * 48)).astype(dtype).reshape(48, 64)
    path = os.path.join(folder, name)
    Image.fromarray(pixels).save(path)
    return path, pixels


class TestWorkingFloatDtype(unittest.TestCase):
    def test_8bit_stays_float16_and_deeper_uses_float32(self) -> None:
        for dtype in (np.uint8, np.int8, np.bool_):
            self.assertIs(working_float_dtype(dtype), np.float16, dtype)
        for dtype in (np.uint16, np.int32, np.uint32, np.float32):
            self.assertIs(working_float_dtype(dtype), np.float32, dtype)


class TestLoadedImagePrecision(unittest.TestCase):
    def _load(self, path: str) -> np.ndarray:
        loader = ImageLoader(image_manager=mock.MagicMock(), imageviewmodel_manager=mock.MagicMock(),
                             settings=AppSettings())
        return loader._load_image_cached(key="Source", image_fullpath=path, mask_fullpath=None).permutations.Image

    def test_8bit_file_loads_as_float16(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path, _ = _write_ramp(tmp, "ramp8.png", np.uint8, 255)
            self.assertEqual(self._load(path).dtype, np.float16)

    def test_16bit_file_keeps_every_level(self) -> None:
        """float16 would round 16-bit levels to 11 significant bits; float32 keeps them all."""
        with tempfile.TemporaryDirectory() as tmp:
            path, pixels = _write_ramp(tmp, "ramp16.png", np.uint16, 65535)
            image = self._load(path)
        self.assertEqual(image.dtype, np.float32)
        np.testing.assert_array_equal(np.round(image.astype(np.float64) * 65535).astype(np.uint16), pixels)

    def test_16bit_file_through_image_view_model_is_float32(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path, _ = _write_ramp(tmp, "ramp16.png", np.uint16, 65535)
            eight_bit_path, _ = _write_ramp(tmp, "ramp8.png", np.uint8, 255)
            self.assertEqual(ImageViewModel(path).Image.dtype, np.float32)
            self.assertEqual(ImageViewModel(eight_bit_path).Image.dtype, np.float16)


if __name__ == "__main__":
    unittest.main()
