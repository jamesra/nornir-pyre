"""Tests for preloaded StosFile in registration helpers."""

from __future__ import annotations

import importlib.util
import os
import unittest
from unittest.mock import MagicMock, patch

import nornir_imageregistration


def _load_stos_registration_module():
    module_path = os.path.normpath(
        os.path.join(os.path.dirname(__file__), os.pardir, "pyre", "stos_registration.py"))
    spec = importlib.util.spec_from_file_location("pyre_stos_registration", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load stos_registration from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_stos_registration = _load_stos_registration_module()
resolve_warped_and_fixed_image_data = _stos_registration.resolve_warped_and_fixed_image_data


class TestStosRegistrationPreloaded(unittest.TestCase):
  """Ensure a preloaded StosFile avoids a second disk load."""

  def test_uses_preloaded_stos_without_loading_file(self) -> None:
    image_manager = MagicMock()
    warped = MagicMock(spec=nornir_imageregistration.ImagePermutationHelper)
    fixed = MagicMock(spec=nornir_imageregistration.ImagePermutationHelper)
    image_manager.__getitem__ = MagicMock(side_effect=lambda key: warped if key == "Source" else fixed)

    stos = MagicMock()
    stos.MappedImageFullPath = r"Y:\mapped.png"
    stos.ControlImageFullPath = r"Y:\control.png"

    with patch.object(_stos_registration, "StosFile") as mock_stos_file:
      warped_out, fixed_out = resolve_warped_and_fixed_image_data(
          image_manager,
          "Source",
          "Target",
          stos_filename=r"Y:\pair.stos",
          stos=stos,
          settings_source_image_path=r"Y:\mapped.png",
          settings_target_image_path=r"Y:\control.png",
      )
      mock_stos_file.Load.assert_not_called()

    self.assertIs(warped_out, warped)
    self.assertIs(fixed_out, fixed)


if __name__ == "__main__":
  unittest.main()
