"""Tests for the Save STOS volume check (find_volume_root, stos_volume_mismatch)."""

from __future__ import annotations

import os
import tempfile
import unittest

from pyre.stos_manual_paths import (
    VOLUME_DATA_FILENAME,
    find_volume_root,
    stos_volume_mismatch,
)


def _norm(path: str) -> str:
    return os.path.normcase(os.path.abspath(path))


def _make_volume(root: str) -> str:
    os.makedirs(root, exist_ok=True)
    with open(os.path.join(root, VOLUME_DATA_FILENAME), "w", encoding="utf-8") as handle:
        handle.write("<Volume />")
    return root


class TestStosVolumeMismatch(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = self._tmp.name
        self.rc1 = _make_volume(os.path.join(base, "RC1_Crush"))
        self.rc3 = _make_volume(os.path.join(base, "RC3"))
        self.no_volume = os.path.join(base, "loose")
        os.makedirs(self.no_volume)
        # The 2026-11-12 incident: an RC3 pair saved into RC1_Crush/TEM/Brute32/Manual.
        self.destination = os.path.join(
            self.rc1, "TEM", "Brute32", "Manual", "122-123_ctrl-TEM_Blob_map-TEM_Blob.stos")
        self.rc1_control = os.path.join(self.rc1, "TEM", "0122", "Blob", "122.png")
        self.rc1_mapped = os.path.join(self.rc1, "TEM", "0123", "Blob", "123.png")
        self.rc3_control = os.path.join(self.rc3, "TEM", "0122", "Blob", "122.png")
        self.rc3_mapped = os.path.join(self.rc3, "TEM", "0123", "Blob", "123.png")

    def test_find_volume_root_walks_up_from_missing_file(self) -> None:
        self.assertEqual(find_volume_root(self.destination), _norm(self.rc1))
        self.assertEqual(find_volume_root(self.rc3_control), _norm(self.rc3))

    def test_find_volume_root_none_outside_volume(self) -> None:
        self.assertIsNone(find_volume_root(os.path.join(self.no_volume, "a.png")))
        self.assertIsNone(find_volume_root(""))

    def test_find_volume_root_uses_nearest_ancestor(self) -> None:
        nested = _make_volume(os.path.join(self.rc1, "TEM", "Nested"))
        self.assertEqual(find_volume_root(os.path.join(nested, "x.stos")), _norm(nested))

    def test_find_volume_root_accepts_unnormalized_paths(self) -> None:
        messy = os.path.join(self.rc1, "TEM", "..", "TEM", "Brute32", "a.stos")
        self.assertEqual(find_volume_root(messy), _norm(self.rc1))

    def test_same_volume_is_not_a_mismatch(self) -> None:
        self.assertIsNone(stos_volume_mismatch(self.destination, [self.rc1_control, self.rc1_mapped]))

    def test_other_volume_images_are_reported(self) -> None:
        mismatch = stos_volume_mismatch(self.destination, [self.rc3_control, self.rc3_mapped])
        self.assertIsNotNone(mismatch)
        assert mismatch is not None
        self.assertEqual(mismatch.destination_volume_root, _norm(self.rc1))
        self.assertEqual(
            mismatch.mismatched_images,
            ((self.rc3_control, _norm(self.rc3)), (self.rc3_mapped, _norm(self.rc3))))

    def test_only_the_foreign_image_is_reported(self) -> None:
        mismatch = stos_volume_mismatch(self.destination, [self.rc1_control, self.rc3_mapped])
        assert mismatch is not None
        self.assertEqual(mismatch.mismatched_images, ((self.rc3_mapped, _norm(self.rc3)),))

    def test_destination_outside_volume_never_warns(self) -> None:
        destination = os.path.join(self.no_volume, "pair.stos")
        self.assertIsNone(stos_volume_mismatch(destination, [self.rc3_control, self.rc3_mapped]))

    def test_images_outside_volume_or_missing_never_warn(self) -> None:
        loose = os.path.join(self.no_volume, "a.png")
        self.assertIsNone(stos_volume_mismatch(self.destination, [loose, None, ""]))


if __name__ == "__main__":
    unittest.main()
