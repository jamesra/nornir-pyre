"""Open-mask menu must update ImageManager slots used by Refine Grid / Spacebar fallback."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import numpy as np

import nornir_imageregistration
from pyre.interfaces.viewtype import ViewType
from pyre.state.managers.image_manager import ImageManager
from pyre.state.stos import StosState
from pyre.viewmodels import ImageViewModel


class TestMaskLoadSyncsImageManager(unittest.TestCase):
    def _state(self) -> StosState:
        return StosState(
            transform_controller=MagicMock(),
            image_manager=ImageManager(),
            image_viewmodel_manager=MagicMock(),
            image_loader=MagicMock(),
            window_manager=MagicMock(),
        )

    def test_load_source_mask_replaces_image_manager_slot_with_masked_helper(self) -> None:
        state = self._state()
        image = np.full((8, 8), 0.5, dtype=np.float32)
        unmasked = nornir_imageregistration.ImagePermutationHelper(image, None)
        state._image_manager.add(key=ViewType.Source, image=unmasked)
        state.SourceImageViewModel = ImageViewModel(image)
        self.assertIsNone(state._image_manager[ViewType.Source].Mask)

        mask = np.ones((8, 8), dtype=bool)
        mask[0:2, :] = False
        mask_vm = ImageViewModel(mask.astype(np.float32))
        with patch("pyre.state.stos.LoadImage", return_value=mask_vm):
            state.LoadFixedMaskImage("mask.png")

        slot = state._image_manager[ViewType.Source]
        self.assertIs(slot, state.FixedImages)
        self.assertIsNotNone(slot.Mask)
        self.assertFalse(bool(slot.Mask[0, 0]))
        self.assertTrue(bool(slot.Mask[4, 4]))

    def test_load_source_image_keeps_existing_mask_on_manager_slot(self) -> None:
        state = self._state()
        image = np.full((8, 8), 0.25, dtype=np.float32)
        mask = np.ones((8, 8), dtype=bool)
        mask[:, 0:2] = False
        state.FixedImageMaskViewModel = ImageViewModel(mask.astype(np.float32))

        new_image = np.full((8, 8), 0.75, dtype=np.float32)
        loader_helper = nornir_imageregistration.ImagePermutationHelper(new_image, None)
        load_result = MagicMock()
        load_result.permutations = loader_helper
        load_result.image_converted_from_color = False
        load_result.mask_converted_from_color = False
        state._image_loader.load_image_into_manager.return_value = load_result
        state._image_loader.create_image_viewmodel.return_value = ImageViewModel(new_image)

        # Simulate loader writing the mask-less helper into the manager first.
        state._image_manager.add(key=ViewType.Source, image=loader_helper)

        with patch("pyre.state.stos._warn_rgb_like_paths_converted"):
            state.LoadSourceImage("source.png")

        slot = state._image_manager[ViewType.Source]
        self.assertIs(slot, state.FixedImages)
        self.assertIsNotNone(slot.Mask)
        self.assertFalse(bool(slot.Mask[0, 0]))


if __name__ == "__main__":
    unittest.main()
