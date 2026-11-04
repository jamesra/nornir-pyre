"""RBF tiles update live while a control point is dragged.

Live drag patches tile vertices from a barycentric stencil over the control points.
Only triangulated models got one, and ``TwoWayRBFWithLinearCorrection`` is not
triangulated, so on RBF transforms every patch returned False and the images only
moved when the point was dropped (2026-11-03, after converting a mesh to RBF). RBF tiles
now use the forward RBF's triangulation; their vertices lie on the RBF surface, so the
patch moves each vertex by the change in its stencil value instead of snapping it onto
the triangles.
"""
from __future__ import annotations

import unittest
from types import SimpleNamespace

import numpy as np
from nornir_imageregistration.transforms import ConvertTransform, MeshWithRBFFallback
from nornir_imageregistration.transforms.transform_type import TransformType
from pyre.space import Space
from pyre.views import gltiles


def _warped_mesh() -> MeshWithRBFFallback:
    source = np.array([[y, x] for y in (0.0, 16.0, 32.0) for x in (0.0, 16.0, 32.0)])
    target = source + np.sin(source / 9.0) * 2.0
    return MeshWithRBFFallback(np.hstack((target, source)))


def _rbf():
    return ConvertTransform(_warped_mesh(), TransformType.RBF)


def _render_data(entry) -> SimpleNamespace:
    return SimpleNamespace(
        is_rigid_quad=False,
        mesh_populated=True,
        vertex_buffer=SimpleNamespace(data=np.array(entry.vertices, copy=True)),
        cp_indices=entry.cp_indices,
        cp_weights=np.array(entry.cp_weights, copy=True),
        cp_targets=None if entry.cp_targets is None else np.array(entry.cp_targets, copy=True),
    )


def _target_xy(render_data) -> np.ndarray:
    return np.asarray(render_data.vertex_buffer.data, dtype=np.float64)[:, 0:2]


class TestRbfLiveTilePatch(unittest.TestCase):

    def test_rbf_tiles_get_a_relative_stencil(self):
        rbf = _rbf()
        self.assertEqual(rbf.type, TransformType.RBF)
        entry = gltiles.build_tile_mesh_cpu(rbf, (0, 0), (32, 32), Space.Source, extrapolate=False)
        self.assertIsNotNone(entry.cp_indices)
        self.assertIsNotNone(entry.cp_targets)

    def test_mesh_stencil_stays_absolute(self):
        entry = gltiles.build_tile_mesh_cpu(_warped_mesh(), (0, 0), (32, 32), Space.Source, extrapolate=False)
        self.assertIsNotNone(entry.cp_indices)
        self.assertIsNone(entry.cp_targets)

    def test_target_drag_patches_rbf_tiles(self):
        rbf = _rbf()
        entry = gltiles.build_tile_mesh_cpu(rbf, (0, 0), (32, 32), Space.Source, extrapolate=False)
        render_data = _render_data(entry)
        before = _target_xy(render_data).copy()
        moved = 4
        delta_yx = np.array([3.0, -2.0])
        rbf.UpdateTargetPointsByIndex(moved, np.asarray(rbf.TargetPoints[moved], dtype=np.float64) + delta_yx)

        self.assertTrue(gltiles.try_patch_tile_vertices_from_stencil(
            render_data, rbf.TargetPoints, rbf.SourcePoints, np.array([moved]), Space.Target))

        after = _target_xy(render_data)
        self.assertGreater(float(np.abs(after - before).max()), 0.5, "tiles moved during the drag")
        weight_on_moved = np.where(entry.cp_indices == moved, entry.cp_weights, 0.0).sum(axis=1)
        expected = before + weight_on_moved[:, None] * delta_yx[::-1]
        np.testing.assert_allclose(after, expected, atol=1e-3)
        np.testing.assert_allclose(render_data.cp_targets, rbf.TargetPoints)

    def test_no_jump_when_the_drag_starts(self):
        """A zero-length first patch leaves RBF vertices where the RBF put them."""
        rbf = _rbf()
        entry = gltiles.build_tile_mesh_cpu(rbf, (0, 0), (32, 32), Space.Source, extrapolate=False)
        render_data = _render_data(entry)
        before = _target_xy(render_data).copy()
        self.assertTrue(gltiles.try_patch_tile_vertices_from_stencil(
            render_data, rbf.TargetPoints, rbf.SourcePoints, np.array([4]), Space.Target))
        np.testing.assert_allclose(_target_xy(render_data), before, atol=1e-4)

    def test_patches_accumulate_over_a_drag(self):
        rbf = _rbf()
        entry = gltiles.build_tile_mesh_cpu(rbf, (0, 0), (32, 32), Space.Source, extrapolate=False)
        render_data = _render_data(entry)
        before = _target_xy(render_data).copy()
        start = np.asarray(rbf.TargetPoints[4], dtype=np.float64).copy()
        for step in range(1, 4):
            rbf.UpdateTargetPointsByIndex(4, start + step * np.array([1.0, 0.5]))
            gltiles.try_patch_tile_vertices_from_stencil(
                render_data, rbf.TargetPoints, rbf.SourcePoints, np.array([4]), Space.Target)
        weight_on_moved = np.where(entry.cp_indices == 4, entry.cp_weights, 0.0).sum(axis=1)
        np.testing.assert_allclose(
            _target_xy(render_data), before + weight_on_moved[:, None] * np.array([1.5, 3.0]), atol=1e-3)


if __name__ == '__main__':
    unittest.main()
