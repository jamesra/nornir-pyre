"""Reopening a STOS reuses the loader's decoded images and viewmodels; the cache keeps only the open pair.

James (2026-11-19): File > Open of the STOS being edited made the images disappear instead of reusing them.
The container gave every injection a new ImageLoader, so the caches were always empty.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import MagicMock

import numpy as np
from dependency_injector import providers
from PIL import Image

from pyre.settings import AppSettings
from pyre.state.imageloader import ImageLoader, make_filepath_cache_key


def _loader() -> ImageLoader:
    return ImageLoader(image_manager=MagicMock(), imageviewmodel_manager=MagicMock(), settings=AppSettings())


class TestImageLoaderCache(unittest.TestCase):

    def test_the_stos_container_shares_one_loader(self) -> None:
        from pyre.stos_container import StosContainer
        self.assertIsInstance(StosContainer.image_loader, providers.ThreadSafeSingleton)

    def test_a_reopened_image_reuses_the_decoded_permutations(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, 'a.png')
            Image.fromarray(np.arange(64, dtype=np.uint8).reshape(8, 8)).save(path)
            loader = _loader()

            first = loader._load_image_cached('Source', path, None, [folder])
            second = loader._load_image_cached('Source', path, None, [folder])

            self.assertIs(first.permutations, second.permutations)

    def test_entries_outside_the_open_pair_are_dropped_and_their_textures_freed(self) -> None:
        loader = _loader()
        kept_key = make_filepath_cache_key('kept.png', None)
        dropped_key = make_filepath_cache_key('dropped.png', None)
        kept_vm, dropped_vm = MagicMock(), MagicMock()
        loader._filepath_cache = {kept_key: MagicMock(), dropped_key: MagicMock()}
        loader._viewmodel_cache = {kept_key: kept_vm, dropped_key: dropped_vm}

        loader.release_unused_cache_entries({kept_key})

        self.assertEqual(set(loader._filepath_cache), {kept_key})
        self.assertEqual(loader._viewmodel_cache, {kept_key: kept_vm})
        dropped_vm.release_gpu_resources.assert_called_once()
        kept_vm.release_gpu_resources.assert_not_called()


if __name__ == '__main__':
    unittest.main()
