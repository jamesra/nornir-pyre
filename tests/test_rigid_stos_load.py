"""Tests for Pyre STOS rigid load normalization to CenteredSimilarity2DTransform."""

from __future__ import annotations

import importlib.util
import os
import unittest

import nornir_imageregistration


def _load_stos_registration_module():
    """Import ``pyre.stos_registration`` without initializing the Qt-based pyre package."""
    module_path = os.path.join(
        os.path.dirname(__file__), os.pardir, "pyre", "stos_registration.py"
    )
    spec = importlib.util.spec_from_file_location("pyre_stos_registration", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load stos_registration from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_stos_registration = _load_stos_registration_module()
normalize_rigid_transform_for_pyre_editing = (
    _stos_registration.normalize_rigid_transform_for_pyre_editing
)


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

        normalized = normalize_rigid_transform_for_pyre_editing(loaded)
        self.assertIsInstance(
            normalized, nornir_imageregistration.transforms.CenteredSimilarity2DTransform)
        self.assertAlmostEqual(normalized.scalar, 1.0)
        self.assertTrue(hasattr(normalized, "ScaleWarpedAboutSourcePoint"))

    def test_centered_similarity_load_is_unchanged(self) -> None:
        similarity = nornir_imageregistration.transforms.CenteredSimilarity2DTransform(
            target_offset=(1.0, 2.0),
            source_rotation_center=(0, 0),
            angle=0.05,
            scalar=1.08,
        )
        itk_string = similarity.ToITKString()
        loaded = nornir_imageregistration.transforms.LoadTransform(itk_string)
        normalized = normalize_rigid_transform_for_pyre_editing(loaded)
        self.assertIs(loaded, normalized)
        self.assertAlmostEqual(normalized.scalar, 1.08)

    def test_rotate_translate_rigid_result_supports_scaling(self) -> None:
        """Rotate-translate estimate returns plain Rigid; Pyre must upgrade for Shift+wheel scale."""
        rigid = nornir_imageregistration.transforms.Rigid(
            target_offset=(5.0, -3.0),
            source_rotation_center=(128.0, 128.0),
            angle=12.5,
        )
        normalized = normalize_rigid_transform_for_pyre_editing(rigid)
        self.assertIsInstance(
            normalized, nornir_imageregistration.transforms.CenteredSimilarity2DTransform)
        normalized.ScaleWarpedAboutSourcePoint(1.05, (64.0, 64.0))
        self.assertAlmostEqual(normalized.scalar, 1.0 / 1.05)
