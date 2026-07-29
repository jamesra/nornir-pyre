"""Tests for filepath-keyed ImageViewModel reuse in ImageLoader."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

import numpy as np

import nornir_imageregistration
from pyre.interfaces.action import Action
from pyre.interfaces.named_tuples import ImageLoadResult
from pyre.state.imageloader import ImageLoader, make_filepath_cache_key
from pyre.state.managers.image_viewmodel_manager import ImageViewModelManager


def _sample_image(size: int = 32) -> np.ndarray:
    return np.arange(size * size, dtype=np.float32).reshape(size, size)


def _make_load_result(
        key: str,
        image: np.ndarray,
        image_fullpath: str,
        cache_key: tuple[str, str | None],
) -> ImageLoadResult:
    permutations = nornir_imageregistration.ImagePermutationHelper(image, None)
    return ImageLoadResult(
        key=key,
        permutations=permutations,
        image_fullpath=image_fullpath,
        image_original_fullpath=image_fullpath,
        mask_fullpath=None,
        mask_original_fullpath=None,
        filepath_cache_key=cache_key,
    )


class TestImageViewModelCache(unittest.TestCase):
    """Verify ImageLoader reuses viewmodels for the same resolved filepath."""

    def setUp(self) -> None:
        self.image_manager = MagicMock()
        self.image_manager.__contains__ = MagicMock(return_value=False)
        self.vm_manager = ImageViewModelManager()
        self.loader = ImageLoader.__new__(ImageLoader)
        self.loader._image_manager = self.image_manager
        self.loader._image_viewmodel_manager = self.vm_manager
        self.loader._filepath_cache = {}
        self.loader._viewmodel_cache = {}

    def test_reuses_viewmodel_for_same_filepath_cache_key(self) -> None:
        image = _sample_image(32)
        cache_key = make_filepath_cache_key(r"C:\data\section.png", None)
        source = _make_load_result("Source", image, r"C:\data\section.png", cache_key)
        target = _make_load_result("Target", image, r"C:\data\section.png", cache_key)

        vm_source = self.loader.create_image_viewmodel(load_result=source)
        vm_target = self.loader.create_image_viewmodel(load_result=target)

        self.assertIs(vm_source, vm_target)
        self.assertTrue(vm_source.managed_by_filepath_cache)
        self.assertEqual(len(self.loader._viewmodel_cache), 1)

    def test_assign_slot_noop_when_viewmodel_unchanged(self) -> None:
        events: list[tuple[str, Action]] = []
        self.vm_manager.add_change_event_listener(
            lambda name, action, _model: events.append((name, action)))

        image = _sample_image(16)
        cache_key = make_filepath_cache_key(r"C:\data\a.png", None)
        load_result = _make_load_result("Source", image, r"C:\data\a.png", cache_key)

        self.loader.create_image_viewmodel(load_result=load_result)
        self.loader.create_image_viewmodel(load_result=load_result)

        add_count = sum(1 for _name, action in events if action == Action.ADD)
        self.assertEqual(add_count, 1)

    def test_different_filepaths_create_distinct_viewmodels(self) -> None:
        image_a = _sample_image(16)
        image_b = _sample_image(16) + 1.0
        key_a = make_filepath_cache_key(r"C:\data\a.png", None)
        key_b = make_filepath_cache_key(r"C:\data\b.png", None)

        vm_a = self.loader.create_image_viewmodel(
            load_result=_make_load_result("Source", image_a, r"C:\data\a.png", key_a))
        vm_b = self.loader.create_image_viewmodel(
            load_result=_make_load_result("Target", image_b, r"C:\data\b.png", key_b))

        self.assertIsNot(vm_a, vm_b)
        self.assertEqual(len(self.loader._viewmodel_cache), 2)


if __name__ == "__main__":
    unittest.main()
