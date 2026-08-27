"""Pyre grid refine stays on host arrays while the process lib may be CuPy."""

from __future__ import annotations

import unittest

import numpy as np

import nornir_imageregistration
from nornir_imageregistration.computational_lib import HasCupy
from nornir_imageregistration.mmap_metadata import memmap_metadata
from nornir_imageregistration.refine_shared.progress import snapshot_transform_for_preview

from pyre.common import create_pyre_grid_refinement_settings


class TestPyreGridRefineHost(unittest.TestCase):
    """Worker inputs for Refine w/ Grid must not be CuPy."""

    def _pair_helpers(self) -> tuple[
            nornir_imageregistration.ImagePermutationHelper,
            nornir_imageregistration.ImagePermutationHelper]:
        shape = (64, 64)
        image = np.linspace(0.0, 1.0, shape[0] * shape[1], dtype=np.float32).reshape(shape)
        source = nornir_imageregistration.ImagePermutationHelper(image, None)
        target = nornir_imageregistration.ImagePermutationHelper(image.copy(), None)
        return source, target

    def test_create_pyre_grid_refinement_settings_forces_host(self) -> None:
        previous = nornir_imageregistration.GetActiveComputationLib()
        try:
            if HasCupy():
                nornir_imageregistration.SetActiveComputationLib(
                    nornir_imageregistration.ComputationLib.cupy)
            source, target = self._pair_helpers()
            with create_pyre_grid_refinement_settings(
                    source,
                    target,
                    num_iterations=1,
                    grid_spacing=32,
                    cell_size=32,
                    angles_to_search=[0],
            ) as settings:
                self.assertFalse(settings.cupy_processing)
                self.assertFalse(settings.single_thread_processing)
                self.assertIsInstance(settings.target_image, np.ndarray)
                self.assertIsInstance(settings.source_image, np.ndarray)
                self.assertIsInstance(
                    settings.source_image_meta,
                    (nornir_imageregistration.Shared_Mem_Metadata, memmap_metadata))
                if HasCupy():
                    import cupy as cupy_mod
                    self.assertFalse(isinstance(settings.target_image, cupy_mod.ndarray))
                    self.assertFalse(isinstance(settings.source_image, cupy_mod.ndarray))
        finally:
            nornir_imageregistration.SetActiveComputationLib(previous)

    @unittest.skipUnless(HasCupy(), "requires CuPy")
    def test_pyre_worker_transform_snapshot_is_host_mesh(self) -> None:
        import cupy as cupy_mod

        host = np.array([
            [0.0, 0.0, 0.0, 0.0],
            [0.0, 10.0, 0.0, 10.0],
            [10.0, 0.0, 10.0, 0.0],
            [10.0, 10.0, 12.0, 11.0],
        ], dtype=np.float64)
        live = nornir_imageregistration.transforms.MeshWithRBFFallback_GPUComponent(
            cupy_mod.asarray(host))
        snapshot = snapshot_transform_for_preview(live)
        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertIsInstance(
            snapshot, nornir_imageregistration.transforms.MeshWithRBFFallback)
        self.assertNotIsInstance(
            snapshot, nornir_imageregistration.transforms.MeshWithRBFFallback_GPUComponent)
        snap_points = snapshot.points  # type: ignore[attr-defined]
        self.assertFalse(isinstance(snap_points, cupy_mod.ndarray))
