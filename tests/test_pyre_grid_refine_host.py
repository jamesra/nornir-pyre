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

    def test_as_stos_grid_transform_converts_mesh_to_grid(self) -> None:
        from nornir_imageregistration.transforms.meshwithrbffallback import (
            MeshWithRBFFallback,
        )
        from nornir_imageregistration.transforms.transform_type import TransformType
        from pyre.common import _as_stos_grid_transform

        source, target = self._pair_helpers()
        point_pairs = np.array([
            [0.0, 0.0, 0.0, 0.0],
            [0.0, 64.0, 0.0, 64.0],
            [64.0, 0.0, 64.0, 0.0],
            [64.0, 64.0, 66.0, 65.0],
        ], dtype=np.float64)
        mesh = MeshWithRBFFallback(point_pairs)
        self.assertEqual(mesh.type, TransformType.MESH)
        with create_pyre_grid_refinement_settings(
                source, target, num_iterations=1, grid_spacing=32, cell_size=32,
                angles_to_search=[0],
        ) as settings:
            grid = _as_stos_grid_transform(mesh, settings)
        self.assertEqual(grid.type, TransformType.GRID)

    def test_compute_grid_refine_returns_grid_not_mesh(self) -> None:
        from unittest.mock import patch

        from nornir_imageregistration.transforms.meshwithrbffallback import (
            MeshWithRBFFallback,
        )
        from nornir_imageregistration.transforms.transform_type import TransformType
        from pyre.common import compute_grid_refine_transform

        source, target = self._pair_helpers()
        point_pairs = np.array([
            [0.0, 0.0, 0.0, 0.0],
            [0.0, 64.0, 0.0, 64.0],
            [64.0, 0.0, 64.0, 0.0],
            [64.0, 64.0, 66.0, 65.0],
        ], dtype=np.float64)
        mesh_result = MeshWithRBFFallback(point_pairs)
        rigid = nornir_imageregistration.transforms.CenteredSimilarity2DTransform(
            (0.0, 0.0), (32.0, 32.0), 0.0)

        with create_pyre_grid_refinement_settings(
                source, target, num_iterations=1, grid_spacing=32, cell_size=32,
                angles_to_search=[0],
        ) as settings:
            with patch(
                    'nornir_imageregistration.RefineTransform',
                    return_value=mesh_result) as mock_refine:
                out = compute_grid_refine_transform(rigid, settings, save_plots=False)
            mock_refine.assert_called_once()
        self.assertEqual(out.type, TransformType.GRID)

    def test_preview_convert_skipped_when_flag_off(self) -> None:
        from unittest.mock import patch

        from nornir_imageregistration.transforms.meshwithrbffallback import (
            MeshWithRBFFallback,
        )
        from pyre.common import compute_grid_refine_transform

        source, target = self._pair_helpers()
        point_pairs = np.array([
            [0.0, 0.0, 0.0, 0.0],
            [0.0, 64.0, 0.0, 64.0],
            [64.0, 0.0, 64.0, 0.0],
            [64.0, 64.0, 66.0, 65.0],
        ], dtype=np.float64)
        mesh_result = MeshWithRBFFallback(point_pairs)
        rigid = nornir_imageregistration.transforms.CenteredSimilarity2DTransform(
            (0.0, 0.0), (32.0, 32.0), 0.0)
        previews: list[object] = []

        def _fake_refine(transform, settings=None, progress_callback=None, **kwargs):
            if progress_callback is not None:
                progress_callback(1, 2, "pass", preview=mesh_result)
            return mesh_result

        def _progress(current, total, status, preview=None, **kwargs):
            previews.append(preview)

        with create_pyre_grid_refinement_settings(
                source, target, num_iterations=1, grid_spacing=32, cell_size=32,
                angles_to_search=[0],
        ) as settings:
            with patch(
                    'nornir_imageregistration.RefineTransform',
                    side_effect=_fake_refine):
                with patch(
                        'pyre.common._as_stos_grid_transform',
                        side_effect=lambda transform, settings, prefer_gpu=False: transform
                ) as convert:
                    compute_grid_refine_transform(
                        rigid, settings, progress_callback=_progress, save_plots=False)
        self.assertEqual(1, convert.call_count)
        self.assertEqual(previews, [None])
        convert.assert_called_once()

    def test_preview_convert_runs_when_flag_on(self) -> None:
        from unittest.mock import patch

        from nornir_imageregistration.transforms.meshwithrbffallback import (
            MeshWithRBFFallback,
        )
        from pyre.common import compute_grid_refine_transform

        source, target = self._pair_helpers()
        point_pairs = np.array([
            [0.0, 0.0, 0.0, 0.0],
            [0.0, 64.0, 0.0, 64.0],
            [64.0, 0.0, 64.0, 0.0],
            [64.0, 64.0, 66.0, 65.0],
        ], dtype=np.float64)
        mesh_result = MeshWithRBFFallback(point_pairs)
        rigid = nornir_imageregistration.transforms.CenteredSimilarity2DTransform(
            (0.0, 0.0), (32.0, 32.0), 0.0)
        previews: list[object] = []

        def _fake_refine(transform, settings=None, progress_callback=None, **kwargs):
            if progress_callback is not None:
                progress_callback(1, 2, "pass", preview=mesh_result)
            return mesh_result

        def _progress(current, total, status, preview=None, **kwargs):
            previews.append(preview)

        with create_pyre_grid_refinement_settings(
                source, target, num_iterations=1, grid_spacing=32, cell_size=32,
                angles_to_search=[0],
        ) as settings:
            with patch(
                    'nornir_imageregistration.RefineTransform',
                    side_effect=_fake_refine):
                with patch(
                        'pyre.common._as_stos_grid_transform',
                        side_effect=lambda transform, settings, prefer_gpu=False: transform
                ) as convert:
                    compute_grid_refine_transform(
                        rigid,
                        settings,
                        progress_callback=_progress,
                        save_plots=False,
                        preview_pass_transforms=True,
                        gpu_preview_grid_convert=True,
                    )
        self.assertEqual(2, convert.call_count)
        self.assertEqual(previews, [mesh_result])
        self.assertTrue(convert.call_args_list[0].kwargs.get("prefer_gpu"))

    def test_snapshot_preserves_grid_type(self) -> None:
        from nornir_imageregistration.transforms.transform_type import TransformType

        source, _target = self._pair_helpers()
        grid = nornir_imageregistration.transforms.converters.ConvertTransformToGridTransform(
            nornir_imageregistration.transforms.CenteredSimilarity2DTransform(
                (0.0, 0.0), (32.0, 32.0), 0.0),
            source_image_shape=np.asarray(source.Image.shape[:2], dtype=np.int64),
            cell_size=np.asarray((32, 32), dtype=np.int32),
            grid_spacing=np.asarray((32, 32), dtype=np.int32),
            prefer_gpu=False,
        )
        self.assertEqual(grid.type, TransformType.GRID)
        snapshot = snapshot_transform_for_preview(grid)
        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertEqual(snapshot.type, TransformType.GRID)
