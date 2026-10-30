"""Pool workers must receive a host (CPU) transform, never a live CuPy one.

``host_transform_snapshot`` used to scan only the top level of a transform's
pickle state. GPU grid transforms keep their device arrays one level down, so
the live GPU object was pickled to every worker, which then started CUDA and
compiled kernels (2.6 to 2.9 s) on its first alignment.

The snapshot must map points exactly like the live transform. Alignment
results are compared against a known answer rather than bit-for-bit with the
live transform: the exact-transform ROI candidate is sampled by different GPU
and CPU code in ``nornir_imageregistration``, and those agree only to within
the alignment's own sub-pixel error (both stay within a pixel of the truth).
"""

from __future__ import annotations

import pickle
import unittest
from typing import Any

import nornir_imageregistration
import numpy as np
import scipy.ndimage
from nornir_imageregistration.computational_lib import HasCupy
from nornir_imageregistration.local_distortion_correction import (
    ApproximateRigidTransformByTargetPoints,
)
from nornir_imageregistration.transforms import Rigid

from pyre.controllers.transformcontroller import (
    host_transform_snapshot,
    run_control_point_alignment,
)

_SIZE = 384
_CENTER = _SIZE / 2.0
_ALIGNMENT_AREA = np.array([96, 96], dtype=np.int32)
_ANGLES = np.array([0.0])
_PROBES = np.array([[150.0, 170.0], [200.0, 230.0], [240.0, 160.0]])
# Sub-pixel error of a single alignment on this fixture, measured for both the
# GPU and the CPU transform classes (worst case about 0.7 px).
_PEAK_TOLERANCE_PX = 1.25


def _known_rigid() -> Rigid:
    return Rigid(target_offset=(2.3, -1.7), source_rotation_center=(_CENTER, _CENTER), angle=0.02)


def _pair_through(rigid: Rigid) -> tuple[nornir_imageregistration.ImagePermutationHelper,
                                         nornir_imageregistration.ImagePermutationHelper]:
    """A smooth target and a source sampled through *rigid*, so the true peak is (0, 0)."""
    rng = np.random.default_rng(3)
    target = scipy.ndimage.gaussian_filter(rng.random((_SIZE, _SIZE)), 3.0).astype(np.float32)
    rows, cols = np.mgrid[0:_SIZE, 0:_SIZE]
    source_points = np.column_stack([rows.ravel(), cols.ravel()]).astype(np.float64)
    target_points = nornir_imageregistration.EnsureNumpyArray(rigid.Transform(source_points))
    source = scipy.ndimage.map_coordinates(
        target, [target_points[:, 0], target_points[:, 1]], order=3, mode='reflect')
    source = source.reshape(_SIZE, _SIZE).astype(np.float32)
    mask = np.ones((_SIZE, _SIZE), dtype=bool)
    return (nornir_imageregistration.ImagePermutationHelper(source, mask.copy()),
            nornir_imageregistration.ImagePermutationHelper(target, mask.copy()))


def _gpu_grid(rigid: Rigid) -> nornir_imageregistration.ITransform:
    from nornir_imageregistration.transforms.gridwithrbffallback import (
        GridWithRBFFallback_GPUComponent,
    )

    grid = nornir_imageregistration.ITKGridDivision((_SIZE, _SIZE), cell_size=(64, 64), grid_dims=(7, 7))
    grid.PopulateTargetPoints(rigid)
    return GridWithRBFFallback_GPUComponent(grid)


def _gpu_mesh(rigid: Rigid) -> nornir_imageregistration.ITransform:
    import cupy
    from nornir_imageregistration.transforms.meshwithrbffallback import (
        MeshWithRBFFallback_GPUComponent,
    )

    coords = np.linspace(0.0, _SIZE - 1.0, 7)
    source_points = np.array([[y, x] for y in coords for x in coords], dtype=np.float64)
    target_points = nornir_imageregistration.EnsureNumpyArray(rigid.Transform(source_points))
    return MeshWithRBFFallback_GPUComponent(cupy.asarray(np.hstack([target_points, source_points])))


@unittest.skipUnless(HasCupy(), "requires CuPy and a CUDA device")
class TestHostTransformSnapshotGpu(unittest.TestCase):
    """GPU grid and mesh transforms become CPU transforms with the same mapping."""

    def _assert_host_snapshot(self, live: nornir_imageregistration.ITransform) -> None:
        self.assertIn(b"cupy", pickle.dumps(live, pickle.HIGHEST_PROTOCOL),
                      "fixture should hold device arrays, or this test proves nothing")
        snapshot = host_transform_snapshot(live)
        self.assertIsNot(snapshot, live)
        self.assertFalse(type(snapshot).__name__.endswith("_GPUComponent"), type(snapshot).__name__)
        self.assertNotIn(b"cupy", pickle.dumps(snapshot, pickle.HIGHEST_PROTOCOL),
                         "a CuPy array survived into the worker payload")
        self.assertEqual(snapshot.type, live.type)  # type: ignore[attr-defined]

        def host(array: Any) -> np.ndarray:
            return np.asarray(nornir_imageregistration.EnsureNumpyArray(array), dtype=np.float64)

        np.testing.assert_allclose(host(snapshot.points), host(live.points))  # type: ignore[attr-defined]
        np.testing.assert_allclose(host(snapshot.Transform(_PROBES)), host(live.Transform(_PROBES)), atol=1e-6)
        np.testing.assert_allclose(
            host(snapshot.InverseTransform(_PROBES)), host(live.InverseTransform(_PROBES)), atol=1e-6)
        for probe in _PROBES:
            live_rigid = ApproximateRigidTransformByTargetPoints(
                input_transform=live, target_points=probe, cell_size=_ALIGNMENT_AREA)[0]
            host_rigid = ApproximateRigidTransformByTargetPoints(
                input_transform=snapshot, target_points=probe, cell_size=_ALIGNMENT_AREA)[0]
            self.assertAlmostEqual(float(host_rigid.angle), float(live_rigid.angle), places=6)  # type: ignore[attr-defined]
            np.testing.assert_allclose(host(host_rigid.target_offset),  # type: ignore[attr-defined]
                                       host(live_rigid.target_offset), atol=1e-6)  # type: ignore[attr-defined]

        source, target = _pair_through(_known_rigid())
        for probe in _PROBES:
            for transform in (live, snapshot):
                record = run_control_point_alignment(
                    transform, source, target, _ALIGNMENT_AREA, _ANGLES, probe.copy())
                assert record is not None
                peak = np.asarray(record.peak, dtype=np.float64)  # type: ignore[attr-defined]
                self.assertLess(
                    float(np.abs(peak).max()), _PEAK_TOLERANCE_PX,
                    f"{type(transform).__name__} peak {peak} at {probe}; the true peak is (0, 0)")

    def test_grid_with_rbf_fallback_gpu_component(self) -> None:
        self._assert_host_snapshot(_gpu_grid(_known_rigid()))

    def test_mesh_with_rbf_fallback_gpu_component(self) -> None:
        self._assert_host_snapshot(_gpu_mesh(_known_rigid()))


class TestHostTransformSnapshotCpu(unittest.TestCase):
    """CPU transforms are passed through unchanged (no copy per dispatch)."""

    def test_cpu_mesh_is_returned_as_is(self) -> None:
        from nornir_imageregistration.transforms.meshwithrbffallback import (
            MeshWithRBFFallback,
        )

        points = np.array([[0.0, 0.0, 0.0, 0.0], [0.0, 10.0, 0.0, 10.0],
                           [10.0, 0.0, 10.0, 0.0], [10.0, 10.0, 10.0, 10.0]])
        mesh = MeshWithRBFFallback(points)
        self.assertIs(host_transform_snapshot(mesh), mesh)


if __name__ == "__main__":
    unittest.main()
