"""Tests for Pyre STOS rigid load normalization to CenteredSimilarity2DTransform."""

from __future__ import annotations

import unittest

import nornir_imageregistration


def normalize_stos_transform_for_pyre_editing(
        transform: nornir_imageregistration.ITransform) -> nornir_imageregistration.ITransform:
    """Mirror StosWindow.loadStos upgrade so legacy rigid files support ScaleWarped."""
    if isinstance(transform, (
            nornir_imageregistration.transforms.RigidTranslation,
            nornir_imageregistration.transforms.Rigid,
    )) and not isinstance(transform, nornir_imageregistration.transforms.CenteredSimilarity2DTransform):
        return nornir_imageregistration.transforms.ConvertRigidTransformToCenteredSimilarityTransform(
            transform)
    return transform


class TestRigidStosLoadNormalization(unittest.TestCase):
    """Legacy Rigid2DTransform strings upgrade to CS2D in Pyre."""

    def test_rigid2d_string_upgrades_to_centered_similarity(self) -> None:
        rigid = nornir_imageregistration.transforms.Rigid(
            target_offset=(10.0, 20.0),
            source_rotation_center=(1.0, 2.0),
            angle=0.1,
        )
        itk_string = rigid.ToITKString()
        loaded = nornir_imageregistration.transforms.LoadTransform(itk_string)
        self.assertIsInstance(loaded, nornir_imageregistration.transforms.Rigid)
        self.assertNotIsInstance(
            loaded, nornir_imageregistration.transforms.CenteredSimilarity2DTransform)

        normalized = normalize_stos_transform_for_pyre_editing(loaded)
        self.assertIsInstance(
            normalized, nornir_imageregistration.transforms.CenteredSimilarity2DTransform)
        self.assertAlmostEqual(normalized.scalar, 1.0)
        self.assertTrue(hasattr(normalized, "ScaleWarped"))

    def test_centered_similarity_load_is_unchanged(self) -> None:
        similarity = nornir_imageregistration.transforms.CenteredSimilarity2DTransform(
            target_offset=(1.0, 2.0),
            source_rotation_center=(0, 0),
            angle=0.05,
            scalar=1.08,
        )
        itk_string = similarity.ToITKString()
        loaded = nornir_imageregistration.transforms.LoadTransform(itk_string)
        normalized = normalize_stos_transform_for_pyre_editing(loaded)
        self.assertIs(loaded, normalized)
        self.assertAlmostEqual(normalized.scalar, 1.08)
