"""Tests for background STOS save helpers."""

from __future__ import annotations

import os
import tempfile
import unittest

import nornir_imageregistration
from nornir_imageregistration import StosFile

from pyre.common import (
    build_stos_object_for_save,
    save_stos_object,
    stos_image_dim_from_shape,
)


class TestStosSaveHelpers(unittest.TestCase):
    def test_stos_image_dim_from_shape(self) -> None:
        dims = stos_image_dim_from_shape((480, 640))
        self.assertEqual(dims, [1.0, 1.0, 640, 480])

    def test_save_stos_object_writes_file(self) -> None:
        rigid = nornir_imageregistration.transforms.Rigid(
            target_offset=(0.0, 0.0),
            source_rotation_center=(0.0, 0.0),
            angle=0.0,
        )
        with tempfile.TemporaryDirectory() as tmp:
            target_path = os.path.join(tmp, "fixed.png")
            source_path = os.path.join(tmp, "warped.png")
            stos_obj = build_stos_object_for_save(
                target_path,
                source_path,
                rigid,
                control_image_dim=[1.0, 1.0, 64, 48],
                mapped_image_dim=[1.0, 1.0, 64, 48],
            )
            out_path = os.path.join(tmp, "pair.stos")
            result = save_stos_object(stos_obj, out_path)
            self.assertEqual(result, out_path)
            self.assertTrue(os.path.isfile(out_path))
            loaded = StosFile.Load(out_path)
            self.assertEqual(
                os.path.normpath(loaded.ControlImageFullPath),
                os.path.normpath(target_path),
            )
            self.assertEqual(
                os.path.normpath(loaded.MappedImageFullPath),
                os.path.normpath(source_path),
            )

    def test_dim_prefill_skips_get_image_size_when_files_exist(self) -> None:
        """Pre-set dims must win over network image header reads when paths exist."""
        from unittest.mock import patch

        rigid = nornir_imageregistration.transforms.Rigid(
            target_offset=(0.0, 0.0),
            source_rotation_center=(0.0, 0.0),
            angle=0.0,
        )
        with tempfile.TemporaryDirectory() as tmp:
            target_path = os.path.join(tmp, "fixed.png")
            source_path = os.path.join(tmp, "warped.png")
            open(target_path, "wb").close()
            open(source_path, "wb").close()
            stos_obj = build_stos_object_for_save(
                target_path,
                source_path,
                rigid,
                control_image_dim=[1.0, 1.0, 100, 200],
                mapped_image_dim=[1.0, 1.0, 150, 250],
            )
            out_path = os.path.join(tmp, "prefilled.stos")
            with patch("nornir_imageregistration.files.stosfile.nornir_imageregistration.core.GetImageSize") as mock_size:
                save_stos_object(stos_obj, out_path)
            mock_size.assert_not_called()

    def test_refresh_image_dims_default_still_probes_disk(self) -> None:
        """Default Save() behavior still re-reads dimensions when files exist."""
        from unittest.mock import patch

        rigid = nornir_imageregistration.transforms.Rigid(
            target_offset=(0.0, 0.0),
            source_rotation_center=(0.0, 0.0),
            angle=0.0,
        )
        with tempfile.TemporaryDirectory() as tmp:
            target_path = os.path.join(tmp, "fixed.png")
            source_path = os.path.join(tmp, "warped.png")
            open(target_path, "wb").close()
            open(source_path, "wb").close()
            stos_obj = build_stos_object_for_save(
                target_path,
                source_path,
                rigid,
            )
            out_path = os.path.join(tmp, "default-refresh.stos")
            with patch("nornir_imageregistration.files.stosfile.nornir_imageregistration.core.GetImageSize") as mock_size:
                mock_size.return_value = [4, 4]
                stos_obj.Save(out_path)
            self.assertEqual(mock_size.call_count, 2)

    def test_dim_prefill_allows_save_without_image_files(self) -> None:
        rigid = nornir_imageregistration.transforms.Rigid(
            target_offset=(1.0, 2.0),
            source_rotation_center=(0.0, 0.0),
            angle=0.0,
        )
        missing_target = "D:/no/such/fixed.png"
        missing_source = "D:/no/such/warped.png"
        stos_obj = build_stos_object_for_save(
            missing_target,
            missing_source,
            rigid,
            control_image_dim=[1.0, 1.0, 100, 200],
            mapped_image_dim=[1.0, 1.0, 150, 250],
        )
        with tempfile.TemporaryDirectory() as tmp:
            out_path = os.path.join(tmp, "missing-images.stos")
            save_stos_object(stos_obj, out_path)
            self.assertTrue(os.path.isfile(out_path))
            with open(out_path, encoding="utf-8") as handle:
                lines = [line.strip() for line in handle.readlines()]
            self.assertIn("fixed.png", lines[0])
            self.assertIn("warped.png", lines[1])

    def test_rigid_transform_round_trips_through_save(self) -> None:
        """Saved rigid transforms must reload with the same mapping geometry."""
        import numpy as np

        rigid = nornir_imageregistration.transforms.CenteredSimilarity2DTransform(
            target_offset=(4.0, 6.0),
            source_rotation_center=(12.0, 18.0),
            angle=0.2,
            scalar=1.0,
        )
        sample_points = np.array([[0.0, 0.0], [40.0, 55.0], [120.0, 90.0]], dtype=float)
        expected = rigid.Transform(sample_points)
        with tempfile.TemporaryDirectory() as tmp:
            target_path = os.path.join(tmp, "fixed.png")
            source_path = os.path.join(tmp, "warped.png")
            open(target_path, "wb").close()
            open(source_path, "wb").close()
            stos_obj = build_stos_object_for_save(
                target_path,
                source_path,
                rigid,
                control_image_dim=[1.0, 1.0, 640, 480],
                mapped_image_dim=[1.0, 1.0, 640, 480],
            )
            out_path = os.path.join(tmp, "rigid-roundtrip.stos")
            save_stos_object(stos_obj, out_path)
            loaded = StosFile.Load(out_path)
            reloaded = nornir_imageregistration.transforms.LoadTransform(loaded.Transform)
            np.testing.assert_allclose(reloaded.Transform(sample_points), expected, atol=1e-5)


if __name__ == "__main__":
    unittest.main()
