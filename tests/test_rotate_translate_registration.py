"""Tests for Pyre rotate-translate image orientation and registration."""

from __future__ import annotations

import importlib.util
import os
import unittest

import numpy as np

import nornir_imageregistration
import nornir_imageregistration.stos_brute as stos_brute
from nornir_imageregistration.files.stosfile import StosFile
from nornir_imageregistration.settings import SliceToSliceMethod
from nornir_imageregistration.transforms import LoadTransform


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
resolve_warped_and_fixed_image_data = _stos_registration.resolve_warped_and_fixed_image_data


def _wrap_angle_diff(measured: float, expected: float) -> float:
    """Return the shortest signed difference between two angles in degrees."""
    return (measured - expected + 180.0) % 360.0 - 180.0


class _MinimalImageManager(dict):
    """Minimal mapping used in place of Pyre's ImageManager."""

    def __contains__(self, key: object) -> bool:
        return super().__contains__(str(key))

    def __getitem__(self, key: object):
        return super().__getitem__(str(key))


def _idoc_paths() -> dict[str, str] | None:
    """Return 690/691 fixture paths (bundled) or repro output under TESTOUTPUTPATH."""
    candidates = [
        os.path.join(
            os.path.dirname(__file__), os.pardir, os.pardir,
            "nornir-imageregistration", "tests", "fixtures", "idoc_690_691",
        ),
        os.path.join(
            os.environ.get("TESTOUTPUTPATH", "/tmp/nornir-test-output"),
            "IDocBuildTestBootstrapDebugging", "TEM",
        ),
    ]
    for base in candidates:
        paths = {
            "mapped_image": os.path.join(
                base, "0690", "TEM", "Leveled", "Images", "016", "0690_TEM_Leveled.png"
            ),
            "mapped_mask": os.path.join(
                base, "0690", "TEM", "Mask", "Images", "016", "0690_TEM_Mask.png"
            ),
            "control_image": os.path.join(
                base, "0691", "TEM", "Leveled", "Images", "016", "0691_TEM_Leveled.png"
            ),
            "control_mask": os.path.join(
                base, "0691", "TEM", "Mask", "Images", "016", "0691_TEM_Mask.png"
            ),
            "reference_stos": os.path.join(
                base, "StosBrute16", "690-691_ctrl-TEM_Leveled_map-TEM_Leveled.stos"
            ),
        }
        if all(os.path.isfile(p) for p in paths.values()):
            return paths
    return None


class TestResolveWarpedAndFixed(unittest.TestCase):
    """Verify resolver maps Source=690 mapped, Target=691 control."""

    def setUp(self) -> None:
        self._paths = _idoc_paths()
        if self._paths is None:
            self.skipTest("IDoc 690/691 fixtures not available")

        self._mapped = nornir_imageregistration.ImagePermutationHelper(
            self._paths["mapped_image"], self._paths["mapped_mask"]
        )
        self._control = nornir_imageregistration.ImagePermutationHelper(
            self._paths["control_image"], self._paths["control_mask"]
        )

    def test_stos_paths_assign_690_mapped_691_control(self) -> None:
        manager = _MinimalImageManager()
        manager["Source"] = self._mapped
        manager["Target"] = self._control
        warped, fixed = resolve_warped_and_fixed_image_data(
            manager,
            "Source",
            "Target",
            stos_filename=self._paths["reference_stos"],
            settings_source_image_path=self._paths["mapped_image"],
            settings_target_image_path=self._paths["control_image"],
        )
        self.assertIs(warped, manager["Source"])
        self.assertIs(fixed, manager["Target"])


class TestRotateTranslateRegistration(unittest.TestCase):
    """End-to-end checks against the StosBrute16 reference transform."""

    def setUp(self) -> None:
        self._paths = _idoc_paths()
        if self._paths is None:
            self.skipTest("IDoc 690/691 fixtures not available")
        nornir_imageregistration.SetActiveComputationLib(
            nornir_imageregistration.ComputationLib.numpy
        )
        reference_stos = StosFile.Load(self._paths["reference_stos"])
        self._reference_angle = float(
            np.degrees(LoadTransform(reference_stos.Transform).angle)
        )

    def test_pyre_rotate_translate_matches_stos_brute_reference(self) -> None:
        """Simulate Pyre slots/settings: 690 in Source, 691 in Target, LimitImageSize=818."""
        manager = _MinimalImageManager()
        manager["Source"] = nornir_imageregistration.ImagePermutationHelper(
            self._paths["mapped_image"], self._paths["mapped_mask"])
        manager["Target"] = nornir_imageregistration.ImagePermutationHelper(
            self._paths["control_image"], self._paths["control_mask"])

        warped, fixed = resolve_warped_and_fixed_image_data(
            manager,
            "Source",
            "Target",
            stos_filename=self._paths["reference_stos"],
            settings_source_image_path=self._paths["mapped_image"],
            settings_target_image_path=self._paths["control_image"],
        )

        settings = nornir_imageregistration.settings.StosBruteSettings(
            min_overlap=0.75,
            method=SliceToSliceMethod.LogPolar,
            try_flipped=True,
            larget_dimension=818,
        )
        record = stos_brute.SliceToSliceRigidRegistrationWithPreprocessedImages(
            source_image_data=warped,
            target_image_data=fixed,
            settings=settings,
            SingleThread=True,
        )
        diff = abs(_wrap_angle_diff(record.angle, self._reference_angle))
        self.assertLessEqual(
            diff,
            0.5,
            f"690->691 angle={record.angle:.3f} ref={self._reference_angle:.3f}",
        )

    def test_wrong_direction_does_not_match_reference(self) -> None:
        """691->690 must not match the StosBrute16 reference (~0.87 deg)."""
        mapped = nornir_imageregistration.ImagePermutationHelper(
            self._paths["mapped_image"], self._paths["mapped_mask"])
        control = nornir_imageregistration.ImagePermutationHelper(
            self._paths["control_image"], self._paths["control_mask"])
        settings = nornir_imageregistration.settings.StosBruteSettings(
            min_overlap=0.75,
            method=SliceToSliceMethod.LogPolar,
            try_flipped=False,
            larget_dimension=818,
        )
        record = stos_brute.SliceToSliceRigidRegistrationWithPreprocessedImages(
            control, mapped, settings, SingleThread=True)
        diff = abs(_wrap_angle_diff(record.angle, self._reference_angle))
        self.assertGreater(diff, 1.0)
