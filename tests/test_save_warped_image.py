"""Tests for registered warped image save and composite display helpers."""

from __future__ import annotations

import os
import tempfile
import unittest

import numpy as np
from nornir_imageregistration.transforms import Rigid

import nornir_imageregistration
from nornir_imageregistration.assemble import transform_for_host_assembly
from pyre.common import AssembleHugeRegisteredWarpedImage, SaveRegisteredWarpedImage
from pyre.views.composite_display import apply_rigid_yx, transform_visible_rectangle


class TestSaveRegisteredWarpedImage(unittest.TestCase):
    """Registered image export accepts ndarray shape tuples."""

    def test_assemble_accepts_image_shape_tuple(self) -> None:
        transform = Rigid(target_offset=(0.0, 0.0), source_rotation_center=(0.0, 0.0), angle=0.0)
        warped = np.zeros((8, 12), dtype=np.uint8)
        result = AssembleHugeRegisteredWarpedImage(transform, (16, 20), warped)
        self.assertEqual(result.shape, (16, 20))

    def test_export_fills_unmapped_regions_with_black(self) -> None:
        """Regions outside the warped footprint should export as zero (black), not extrapolated fill."""
        transform = Rigid(target_offset=(0.0, 0.0), source_rotation_center=(0.0, 0.0), angle=0.0)
        warped = np.full((4, 4), 200, dtype=np.uint8)
        result = AssembleHugeRegisteredWarpedImage(transform, (8, 8), warped)
        np.testing.assert_array_equal(result[:4, :4], 200)
        np.testing.assert_array_equal(result[4:, :], 0)
        np.testing.assert_array_equal(result[:, 4:], 0)

    def test_save_registered_warped_image_writes_png(self) -> None:
        transform = Rigid(target_offset=(0.0, 0.0), source_rotation_center=(0.0, 0.0), angle=0.0)
        warped = np.arange(64, dtype=np.uint8).reshape(8, 8)
        with tempfile.TemporaryDirectory() as tmp:
            out_path = os.path.join(tmp, "registered.png")
            SaveRegisteredWarpedImage(out_path, transform, (8, 8), warped)
            self.assertTrue(os.path.isfile(out_path))

    def test_save_registered_warped_image_float16_png(self) -> None:
        """float16 warped inputs must export without Pillow dtype errors."""
        transform = Rigid(target_offset=(0.0, 0.0), source_rotation_center=(0.0, 0.0), angle=0.0)
        warped = np.linspace(0.0, 1.0, 64, dtype=np.float16).reshape(8, 8)
        with tempfile.TemporaryDirectory() as tmp:
            out_path = os.path.join(tmp, "registered_f16.png")
            SaveRegisteredWarpedImage(out_path, transform, (8, 8), warped)
            self.assertTrue(os.path.isfile(out_path))

    def test_save_registered_warped_image_float16_raw_intensity_png(self) -> None:
        """float16 EM-style intensities (not 0..1) should not be scaled by 2**32-1."""
        transform = Rigid(target_offset=(0.0, 0.0), source_rotation_center=(0.0, 0.0), angle=0.0)
        warped = np.array([[0.0, 1000.0], [2500.0, 4000.0]], dtype=np.float16)
        with tempfile.TemporaryDirectory() as tmp:
            out_path = os.path.join(tmp, "registered_raw_f16.png")
            SaveRegisteredWarpedImage(out_path, transform, (2, 2), warped)
            loaded = nornir_imageregistration.EnsureNumpyArray(
                nornir_imageregistration.LoadImage(out_path, dtype=np.uint16))
            np.testing.assert_array_equal(loaded, np.array([[0, 1000], [2500, 4000]], dtype=np.uint16))


class TestTransformForHostAssembly(unittest.TestCase):
    """GPU grid transforms must convert to CPU before tiled export."""

    def test_grid_gpu_component_converts_to_cpu_grid(self) -> None:
        try:
            from nornir_imageregistration.transforms.gridwithrbffallback import (
                GridWithRBFFallback,
                GridWithRBFFallback_GPUComponent,
            )
        except ImportError:
            self.skipTest("Grid transform modules unavailable")

        if not nornir_imageregistration.HasCupy():
            self.skipTest("CuPy not available")

        grid = nornir_imageregistration.ITKGridDivision((32, 32), cell_size=(16, 16))
        rigid = Rigid(target_offset=(1.0, 2.0), source_rotation_center=(8.0, 8.0), angle=0.1)
        grid.PopulateTargetPoints(rigid)
        gpu = GridWithRBFFallback_GPUComponent(grid)
        host = transform_for_host_assembly(gpu)
        self.assertIsInstance(host, GridWithRBFFallback)
        self.assertFalse(type(host).__name__.endswith('_GPUComponent'))


class TestCompositeDisplay(unittest.TestCase):
    """Composite draw helpers map source-space camera bounds to target space."""

    def test_identity_transform_preserves_rectangle(self) -> None:
        rect = nornir_imageregistration.Rectangle.CreateFromBounds((10.0, 20.0, 30.0, 40.0))
        identity = np.eye(3, dtype=np.float32)
        mapped = transform_visible_rectangle(rect, identity)
        self.assertAlmostEqual(float(mapped.BottomLeft[0]), 10.0)
        self.assertAlmostEqual(float(mapped.BottomLeft[1]), 20.0)
        self.assertAlmostEqual(float(mapped.TopRight[0]), 30.0)
        self.assertAlmostEqual(float(mapped.TopRight[1]), 40.0)

    def test_translation_shifts_visible_bounds(self) -> None:
        rect = nornir_imageregistration.Rectangle.CreateFromBounds((0.0, 0.0, 10.0, 10.0))
        translate = np.array([
            [1.0, 0.0, 5.0],
            [0.0, 1.0, 7.0],
            [0.0, 0.0, 1.0],
        ], dtype=np.float32)
        point = apply_rigid_yx(translate, np.array([0.0, 0.0]))
        self.assertAlmostEqual(float(point[0]), 5.0)
        self.assertAlmostEqual(float(point[1]), 7.0)
        mapped = transform_visible_rectangle(rect, translate)
        self.assertAlmostEqual(float(mapped.BottomLeft[0]), 5.0)
        self.assertAlmostEqual(float(mapped.BottomLeft[1]), 7.0)


if __name__ == "__main__":
    unittest.main()
