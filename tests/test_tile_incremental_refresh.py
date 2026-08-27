"""Tests for incremental tile refresh during control-point drag."""

import unittest
from unittest.mock import MagicMock, patch

import numpy as np
from hypothesis import example, given, settings
from hypothesis import strategies as st

import nornir_imageregistration
from nornir_imageregistration.grid_subdivision import ITKGridDivision
from nornir_imageregistration.transforms import Rigid
from nornir_imageregistration.transforms.gridtransform import GridTransform
from nornir_imageregistration.transforms.gridwithrbffallback import GridWithRBFFallback
from nornir_imageregistration.transforms.meshwithrbffallback import MeshWithRBFFallback
from nornir_imageregistration.transforms.triangulation import (
    apply_barycentric_stencil,
    barycentric_sample_delaunay,
    barycentric_stencil_delaunay,
    barycentric_weights_in_triangle,
)
from pyre.controllers.tile_mesh_cache import TileMeshCpuCache, TileMeshCpuEntry
from pyre.space import Space
from pyre.views import gltiles


def _identity_grid() -> GridTransform:
    grid = ITKGridDivision(source_shape=(32, 32), cell_size=(16, 16))
    grid.PopulateTargetPoints(
        Rigid(target_offset=(0.0, 0.0), source_rotation_center=(16.0, 16.0), angle=0.0))
    return GridTransform(grid)


def _rotated_grid(
        source_shape: tuple[int, int] = (80, 80),
        cell_size: tuple[int, int] = (13, 13)) -> GridTransform:
    grid = ITKGridDivision(source_shape=source_shape, cell_size=cell_size)
    cy = source_shape[0] / 2.0
    cx = source_shape[1] / 2.0
    grid.PopulateTargetPoints(
        Rigid(target_offset=(1.25, -0.75), source_rotation_center=(cy, cx), angle=0.15))
    return GridTransform(grid)


def _tile_rect(y0: float, x0: float, y1: float, x1: float) -> nornir_imageregistration.Rectangle:
    return nornir_imageregistration.Rectangle.CreateFromBounds(np.array((y0, x0, y1, x1)))


def _control_points_inside_tile(
        transform: GridTransform,
        y0: float,
        x0: float,
        y1: float,
        x1: float) -> tuple[np.ndarray, np.ndarray]:
    source = np.asarray(transform.SourcePoints, dtype=np.float64)
    target = np.asarray(transform.TargetPoints, dtype=np.float64)
    inside = (
        (source[:, 0] >= y0) & (source[:, 0] <= y1)
        & (source[:, 1] >= x0) & (source[:, 1] <= x1))
    return source[inside], target[inside]


def _identity_grid_with_rbf() -> GridWithRBFFallback:
    grid = ITKGridDivision(source_shape=(32, 32), cell_size=(16, 16))
    grid.PopulateTargetPoints(
        Rigid(target_offset=(0.0, 0.0), source_rotation_center=(16.0, 16.0), angle=0.0))
    return GridWithRBFFallback(grid)


def _identity_mesh() -> MeshWithRBFFallback:
    points = np.array(
        [
            [0.0, 0.0, 0.0, 0.0],
            [0.0, 32.0, 0.0, 32.0],
            [32.0, 0.0, 32.0, 0.0],
            [32.0, 32.0, 32.0, 32.0],
        ],
        dtype=np.float64,
    )
    return MeshWithRBFFallback(points)


def _pack_tile_vertices(target_yx: np.ndarray, source_yx: np.ndarray) -> np.ndarray:
    verts = np.zeros((target_yx.shape[0], 8), dtype=np.float32)
    verts[:, 0] = target_yx[:, 1]
    verts[:, 1] = target_yx[:, 0]
    verts[:, 3] = source_yx[:, 1]
    verts[:, 4] = source_yx[:, 0]
    return verts


class TestSimplicesCompatibility(unittest.TestCase):
    """Cached Delaunay topology must not be reused after point-count changes."""

    def test_rejects_stale_high_indices(self) -> None:
        simplices = np.array([[0, 1, 947]], dtype=np.intp)
        self.assertFalse(gltiles._simplices_compatible_with_points(simplices, 85, 948))

    def test_accepts_matching_count_and_indices(self) -> None:
        simplices = np.array([[0, 1, 2], [1, 2, 3]], dtype=np.intp)
        self.assertTrue(gltiles._simplices_compatible_with_points(simplices, 4, 4))


class TestTileCoordsForControlPoints(unittest.TestCase):
    """tile_coords_for_control_points must cover both fixed and warped columns."""

    def test_includes_fixed_and_warped_tile_locations(self) -> None:
        points = np.array(
            [
                [100.0, 100.0, 500.0, 500.0],
                [2000.0, 2000.0, 50.0, 50.0],
                [3000.0, 3000.0, 3000.0, 3000.0],
            ],
            dtype=np.float64,
        )
        transform = MeshWithRBFFallback(points)
        texture_size = (256, 256)
        coords = gltiles.tile_coords_for_control_points(
            4096, 4096, texture_size, np.array([0, 1], dtype=np.intp), transform)

        self.assertIn((0, 0), coords)  # index 0 fixed at (100,100)
        self.assertIn((1, 1), coords)  # index 1 warped at (50,50) -> tile (1,1) with halo


class TestTileMeshCacheInvalidation(unittest.TestCase):
    """Stale CPU mesh entries must be dropped before incremental GL upload."""

    def test_invalidate_tiles_removes_matching_entries(self) -> None:
        cache = TileMeshCpuCache()
        entry = TileMeshCpuEntry(
            vertices=np.zeros((4, 8), dtype=np.float32),
            indices=np.arange(6, dtype=np.uint16),
        )
        cache.put(1, Space.Source, (0, 0), entry)
        cache.put(1, Space.Target, (1, 1), entry)
        gen_before = cache.generation

        cache.invalidate_tiles({(0, 0)})

        self.assertIsNone(cache.get(1, Space.Source, (0, 0)))
        self.assertIsNotNone(cache.get(1, Space.Target, (1, 1)))
        self.assertGreater(cache.generation, gen_before)


class TestTransformModelReplaceClearsMeshCache(unittest.TestCase):
    """Rigid→grid convert must not keep identity quads in the shared CPU cache."""

    def test_replacing_model_clears_tile_mesh_cache(self) -> None:
        from nornir_imageregistration.transforms import CenteredSimilarity2DTransform, ConvertTransform
        from nornir_imageregistration.transforms.transform_type import TransformType
        from pyre.controllers.transformcontroller import TransformController

        rigid = CenteredSimilarity2DTransform(
            target_offset=(10.0, 20.0),
            source_rotation_center=(0.0, 0.0),
            angle=0.1,
            scalar=1.0,
        )
        controller = TransformController(rigid)
        stale = TileMeshCpuEntry(
            vertices=np.zeros((4, 8), dtype=np.float32),
            indices=np.arange(6, dtype=np.uint16),
            is_rigid_quad=True,
        )
        controller.tile_mesh_cache.put(99, Space.Source, (0, 0), stale)
        self.assertIsNotNone(controller.tile_mesh_cache.get(99, Space.Source, (0, 0)))

        grid = ConvertTransform(
            rigid, TransformType.GRID, source_image_shape=(64, 64), grid_dims=(3, 3))
        controller.TransformModel = grid

        self.assertIsNone(controller.tile_mesh_cache.get(99, Space.Source, (0, 0)))
        self.assertFalse(controller.display_strategy.uses_static_tile_quads())


class TestRejectCachedRigidQuadWhenWarpRequired(unittest.TestCase):
    """Composite source must not reuse rigid quads after convert-to-grid."""

    def test_get_or_build_ignores_rigid_quad_when_deformable_required(self) -> None:
        from unittest.mock import MagicMock, patch

        from pyre.views.imagetransformview import ImageTransformView

        view = ImageTransformView.__new__(ImageTransformView)
        view._transform_controller = MagicMock()
        view._transform_controller.display_strategy.uses_static_tile_quads.return_value = False
        view._image_space = Space.Source
        view._warp_into_target_display = True
        view._image_viewmodel = MagicMock()
        view._image_viewmodel.TextureSize = np.array([64, 64], dtype=np.int32)
        cache = TileMeshCpuCache()
        stale = TileMeshCpuEntry(
            vertices=np.zeros((4, 8), dtype=np.float32),
            indices=np.arange(6, dtype=np.uint16),
            is_rigid_quad=True,
        )
        cache.put(1, Space.Source, (0, 0), stale)
        view._transform_controller.tile_mesh_cache = cache
        view._view_model_cache_id = MagicMock(return_value=1)  # type: ignore[method-assign]
        view.get_or_create_tile_globjects = MagicMock(return_value=None)
        mesh_transform = MagicMock()
        rebuilt = TileMeshCpuEntry(
            vertices=np.ones((4, 8), dtype=np.float32),
            indices=np.arange(6, dtype=np.uint16),
            is_rigid_quad=False,
        )
        with patch.object(ImageTransformView, "transform", new_callable=lambda: property(lambda self: mesh_transform)):
            with patch("pyre.views.gltiles.is_rigid_transform", return_value=False):
                with patch("pyre.views.gltiles.build_tile_mesh_cpu", return_value=rebuilt) as build:
                    entry = view._get_or_build_cpu_entry((0, 0))
        build.assert_called_once()
        self.assertFalse(entry.is_rigid_quad)
        self.assertIs(cache.get(1, Space.Source, (0, 0)), rebuilt)


class TestRegularGridSimplices(unittest.TestCase):
    """Grid tile meshes use a regular lattice triangulation, not Qhull."""

    def test_cell_count_matches_lattice(self) -> None:
        simplices = gltiles._regular_grid_cell_simplices(5, 4)
        self.assertEqual(simplices.shape, ((5 - 1) * (4 - 1) * 2, 3))
        self.assertEqual(int(simplices.max()), 5 * 4 - 1)

    def test_identity_grid_tile_mesh_skips_delaunay(self) -> None:
        transform = _identity_grid()
        rect = nornir_imageregistration.Rectangle.CreateFromBounds(np.array((0.0, 0.0, 32.0, 32.0)))
        mesh = gltiles._grid_tile_mesh_point_pairs(transform, rect)
        self.assertIsNotNone(mesh)
        assert mesh is not None
        pairs, simplices = mesh
        self.assertGreater(simplices.shape[0], 0)
        self.assertEqual(pairs.shape[1], 4)

    def test_misaligned_tile_includes_interior_control_points(self) -> None:
        transform = _rotated_grid()
        y0, x0, y1, x1 = 5.0, 7.0, 37.0, 39.0
        mesh = gltiles._grid_tile_mesh_point_pairs(transform, _tile_rect(y0, x0, y1, x1))
        self.assertIsNotNone(mesh)
        assert mesh is not None
        pairs, _simplices = mesh
        src = pairs[:, 2:4]
        tgt = pairs[:, 0:2]
        inside_src, inside_tgt = _control_points_inside_tile(transform, y0, x0, y1, x1)
        self.assertGreater(inside_src.shape[0], 0)
        for source_yx, target_yx in zip(inside_src, inside_tgt):
            match = np.all(np.isclose(src, source_yx, atol=1e-6, rtol=0.0), axis=1)
            self.assertTrue(np.any(match), msg=f"missing control point at source {source_yx}")
            np.testing.assert_allclose(tgt[match][0], target_yx, atol=1e-5, rtol=1e-6)
        np.testing.assert_allclose(src[:, 0].min(), y0, atol=1e-9)
        np.testing.assert_allclose(src[:, 0].max(), y1, atol=1e-9)
        np.testing.assert_allclose(src[:, 1].min(), x0, atol=1e-9)
        np.testing.assert_allclose(src[:, 1].max(), x1, atol=1e-9)

    def test_adjacent_tiles_share_warped_edge(self) -> None:
        transform = _rotated_grid()
        left = gltiles._grid_tile_mesh_point_pairs(transform, _tile_rect(0.0, 0.0, 40.0, 40.0))
        right = gltiles._grid_tile_mesh_point_pairs(transform, _tile_rect(0.0, 40.0, 40.0, 80.0))
        self.assertIsNotNone(left)
        self.assertIsNotNone(right)
        assert left is not None and right is not None
        left_edge = left[0][np.isclose(left[0][:, 3], 40.0)]
        right_edge = right[0][np.isclose(right[0][:, 3], 40.0)]
        left_edge = left_edge[np.argsort(left_edge[:, 2])]
        right_edge = right_edge[np.argsort(right_edge[:, 2])]
        np.testing.assert_allclose(left_edge, right_edge, atol=1e-6, rtol=1e-6)

    @given(
        y0=st.integers(0, 400).map(lambda v: v / 10.0),
        x0=st.integers(0, 400).map(lambda v: v / 10.0),
    )
    @example(y0=0.0, x0=0.0)
    @example(y0=5.0, x0=7.0)
    @settings(max_examples=25, deadline=None)
    def test_tile_mesh_contains_every_in_tile_control_point(self, y0: float, x0: float) -> None:
        transform = _rotated_grid()
        y1 = y0 + 32.0
        x1 = x0 + 32.0
        mesh = gltiles._grid_tile_mesh_point_pairs(transform, _tile_rect(y0, x0, y1, x1))
        self.assertIsNotNone(mesh)
        assert mesh is not None
        pairs, _simplices = mesh
        src = pairs[:, 2:4]
        inside_src, _inside_tgt = _control_points_inside_tile(transform, y0, x0, y1, x1)
        for source_yx in inside_src:
            match = np.all(np.isclose(src, source_yx, atol=1e-6, rtol=0.0), axis=1)
            self.assertTrue(np.any(match), msg=f"missing control point at source {source_yx}")
        outside = np.asarray(transform.SourcePoints, dtype=np.float64)
        # CPs on the closed tile, or closer than a texel-scale epsilon to an
        # edge sample, are not halo; those vertices are the shared seam.
        halo = 1e-4
        outside = outside[
            (outside[:, 0] < y0 - halo) | (outside[:, 0] > y1 + halo)
            | (outside[:, 1] < x0 - halo) | (outside[:, 1] > x1 + halo)]
        for source_yx in outside:
            match = np.all(np.isclose(src, source_yx, atol=1e-6, rtol=0.0), axis=1)
            self.assertFalse(np.any(match), msg=f"halo control point {source_yx} leaked into tile mesh")


class TestInteractiveControlPointVertexPatch(unittest.TestCase):
    """CP drag must map live TargetPoints onto existing vertices without Transform()."""

    def test_grid_mapper_matches_target_points_at_nodes(self) -> None:
        transform = _identity_grid()
        mapper = gltiles.source_to_target_mapper_for_interactive_drag(transform)
        self.assertIsNotNone(mapper)
        assert mapper is not None
        mapped = mapper(transform.SourcePoints)
        np.testing.assert_allclose(mapped, transform.TargetPoints, rtol=1e-6, atol=1e-6)

    def test_grid_mapper_does_not_call_transform(self) -> None:
        transform = _identity_grid_with_rbf()
        with patch.object(transform, "Transform", side_effect=AssertionError("Transform()")):
            mapper = gltiles.source_to_target_mapper_for_interactive_drag(transform)
            self.assertIsNotNone(mapper)
            assert mapper is not None
            mapped = mapper(transform.SourcePoints)
        np.testing.assert_allclose(mapped, transform.TargetPoints, rtol=1e-6, atol=1e-6)

    @given(
        dy=st.floats(-8.0, 8.0, allow_nan=False, allow_infinity=False),
        dx=st.floats(-8.0, 8.0, allow_nan=False, allow_infinity=False),
    )
    @example(dy=0.0, dx=0.0)
    @example(dy=5.0, dx=-3.0)
    @settings(max_examples=20, deadline=None)
    def test_grid_mapper_follows_moved_control_point(self, dy: float, dx: float) -> None:
        transform = _identity_grid()
        source = np.array(transform.SourcePoints, copy=True)
        new_target = transform.TargetPoints[0] + np.array((dy, dx), dtype=np.float64)
        transform.UpdateTargetPointsByIndex(0, new_target)
        mapper = gltiles.source_to_target_mapper_for_interactive_drag(transform)
        self.assertIsNotNone(mapper)
        assert mapper is not None
        mapped = mapper(source)
        np.testing.assert_allclose(mapped[0], new_target, rtol=1e-6, atol=1e-5)
        np.testing.assert_allclose(mapped[1:], transform.TargetPoints[1:], rtol=1e-6, atol=1e-5)

    def test_patch_updates_target_xy_from_live_control_points(self) -> None:
        transform = _identity_grid()
        source = np.array(transform.SourcePoints, copy=True)
        verts = _pack_tile_vertices(transform.TargetPoints, source)
        transform.UpdateTargetPointsByIndex(0, transform.TargetPoints[0] + np.array((4.0, -2.0)))
        mapper = gltiles.source_to_target_mapper_for_interactive_drag(transform)
        self.assertIsNotNone(mapper)
        assert mapper is not None
        patched = gltiles.patch_tile_vertices_from_control_points(verts, mapper)
        self.assertIsNotNone(patched)
        assert patched is not None
        np.testing.assert_allclose(patched[:, 3:5], verts[:, 3:5])
        np.testing.assert_allclose(
            np.column_stack((patched[:, 1], patched[:, 0])),
            transform.TargetPoints,
            rtol=1e-6,
            atol=1e-5,
        )

    def test_interactive_update_skips_remesh_when_patch_succeeds(self) -> None:
        from pyre.views.imagetransformview import ImageTransformView

        transform = _identity_grid()
        view = ImageTransformView.__new__(ImageTransformView)
        view._transform_controller = MagicMock()
        view._transform_controller.interactive_edit_in_progress = True
        view._transform_controller.tile_mesh_cache = TileMeshCpuCache()
        view._image_space = Space.Source
        view._warp_into_target_display = True
        view._image_viewmodel = MagicMock()
        view._image_viewmodel.TextureSize = np.array([64, 64], dtype=np.int32)
        view._image_viewmodel.width = 32
        view._image_viewmodel.height = 32
        view._activate_context = MagicMock()
        render_data = MagicMock()
        render_data.is_rigid_quad = False
        render_data.mesh_populated = True
        render_data.vertex_buffer.data = _pack_tile_vertices(
            transform.TargetPoints, transform.SourcePoints)
        view._tile_render_data = {(0, 0): render_data}
        with patch.object(ImageTransformView, "transform", new_callable=lambda: property(lambda self: transform)):
            with patch("pyre.views.gltiles._update_tile_buffers") as remesh:
                view.update_tiles_for_point_indices(np.array([0], dtype=np.intp))
        remesh.assert_not_called()
        patched = np.asarray(render_data.vertex_buffer.data)
        self.assertEqual(patched.shape[1], 8)

    def test_mesh_mapper_matches_target_points_at_nodes(self) -> None:
        transform = _identity_mesh()
        mapper = gltiles.source_to_target_mapper_for_interactive_drag(transform)
        self.assertIsNotNone(mapper)
        assert mapper is not None
        mapped = mapper(np.asarray(transform.SourcePoints))
        np.testing.assert_allclose(mapped, np.asarray(transform.TargetPoints), rtol=1e-6, atol=1e-5)

    def test_mesh_mapper_does_not_call_transform(self) -> None:
        transform = _identity_mesh()
        with patch.object(transform, "Transform", side_effect=AssertionError("Transform()")):
            mapper = gltiles.source_to_target_mapper_for_interactive_drag(transform)
            self.assertIsNotNone(mapper)
            assert mapper is not None
            mapped = mapper(np.asarray(transform.SourcePoints))
        np.testing.assert_allclose(mapped, np.asarray(transform.TargetPoints), rtol=1e-6, atol=1e-5)

    def test_mesh_mapper_reuses_cached_source_delaunay(self) -> None:
        transform = _identity_mesh()
        _ = transform.source_space_trianglulation
        with patch("pyre.views.gltiles.scipy.spatial.Delaunay", side_effect=AssertionError("Qhull")):
            mapper = gltiles.source_to_target_mapper_for_interactive_drag(transform)
            self.assertIsNotNone(mapper)
            assert mapper is not None
            mapped = mapper(np.asarray(transform.SourcePoints))
        np.testing.assert_allclose(mapped, np.asarray(transform.TargetPoints), rtol=1e-6, atol=1e-5)

    @example(dy=0.0, dx=0.0)
    @example(dy=5.0, dx=-3.0)
    @given(
        dy=st.floats(-8.0, 8.0, allow_nan=False, allow_infinity=False),
        dx=st.floats(-8.0, 8.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=20, deadline=None)
    def test_mesh_mapper_follows_moved_control_point(self, dy: float, dx: float) -> None:
        transform = _identity_mesh()
        source = np.asarray(transform.SourcePoints, dtype=np.float64)
        new_target = np.asarray(transform.TargetPoints[0], dtype=np.float64) + np.array((dy, dx), dtype=np.float64)
        transform.UpdateTargetPointsByIndex(0, new_target)
        mapper = gltiles.source_to_target_mapper_for_interactive_drag(transform)
        self.assertIsNotNone(mapper)
        assert mapper is not None
        mapped = mapper(source)
        np.testing.assert_allclose(mapped[0], new_target, rtol=1e-6, atol=1e-5)
        np.testing.assert_allclose(
            mapped[1:], np.asarray(transform.TargetPoints[1:]), rtol=1e-6, atol=1e-5)

    def test_interactive_mesh_update_skips_remesh_when_patch_succeeds(self) -> None:
        from pyre.views.imagetransformview import ImageTransformView

        transform = _identity_mesh()
        source = np.asarray(transform.SourcePoints)
        target = np.asarray(transform.TargetPoints)
        delaunay = transform.source_space_trianglulation
        cp_indices, cp_weights = barycentric_stencil_delaunay(source, delaunay)
        view = ImageTransformView.__new__(ImageTransformView)
        view._transform_controller = MagicMock()
        view._transform_controller.interactive_edit_in_progress = True
        view._transform_controller.interactive_edit_space = Space.Target
        view._transform_controller.tile_mesh_cache = TileMeshCpuCache()
        view._image_space = Space.Source
        view._warp_into_target_display = True
        view._image_viewmodel = MagicMock()
        view._image_viewmodel.TextureSize = np.array([64, 64], dtype=np.int32)
        view._image_viewmodel.width = 32
        view._image_viewmodel.height = 32
        view._activate_context = MagicMock()
        render_data = MagicMock()
        render_data.is_rigid_quad = False
        render_data.mesh_populated = True
        render_data.cp_indices = cp_indices
        render_data.cp_weights = cp_weights
        render_data.vertex_buffer.data = _pack_tile_vertices(target, source)
        view._tile_render_data = {(0, 0): render_data}
        with patch.object(ImageTransformView, "transform", new_callable=lambda: property(lambda self: transform)):
            with patch("pyre.views.gltiles._update_tile_buffers") as remesh:
                view.update_tiles_for_point_indices(np.array([0], dtype=np.intp))
        remesh.assert_not_called()

    def test_interactive_mesh_update_skips_remesh_when_patch_fails(self) -> None:
        from pyre.views.imagetransformview import ImageTransformView

        transform = _identity_mesh()
        view = ImageTransformView.__new__(ImageTransformView)
        view._transform_controller = MagicMock()
        view._transform_controller.interactive_edit_in_progress = True
        view._transform_controller.rbf_prewarm_ready = True
        view._transform_controller.tile_mesh_cache = TileMeshCpuCache()
        view._image_space = Space.Source
        view._warp_into_target_display = True
        view._image_viewmodel = MagicMock()
        view._image_viewmodel.TextureSize = np.array([64, 64], dtype=np.int32)
        view._image_viewmodel.width = 32
        view._image_viewmodel.height = 32
        view._activate_context = MagicMock()
        render_data = MagicMock()
        render_data.is_rigid_quad = False
        render_data.mesh_populated = False
        view._tile_render_data = {(0, 0): render_data}
        with patch.object(ImageTransformView, "transform", new_callable=lambda: property(lambda self: transform)):
            with patch("pyre.views.gltiles._update_tile_buffers") as remesh:
                view.update_tiles_for_point_indices(np.array([0], dtype=np.intp))
        remesh.assert_not_called()
        self.assertIsNone(transform._ForwardRBFInstance)

    def test_interactive_point_move_marks_post_drag_remesh(self) -> None:
        from pyre.controllers.transformcontroller import TransformController

        controller = TransformController(_identity_grid())
        controller.begin_interactive_edit(Space.Target)
        try:
            controller.MovePoint(0, 1.0, 2.0, space=Space.Target)
            self.assertTrue(controller._full_refresh_needed)
        finally:
            controller.end_interactive_edit()

    def test_mesh_mouse_up_defers_remesh_until_prewarm_install(self) -> None:
        from pyre.controllers.transformcontroller import TransformController

        controller = TransformController(_identity_mesh())
        controller.begin_interactive_edit(Space.Target)
        try:
            controller.MovePoint(0, 1.0, 2.0, space=Space.Target)
            with patch.object(controller, "_queue_rbf_prewarm") as queue:
                with patch.object(controller, "FireOnChangeEvent") as fire:
                    controller.end_interactive_edit()
            queue.assert_called_once()
            fire.assert_not_called()
            self.assertTrue(controller._hold_composite_display_until_prewarm)
        finally:
            if controller.interactive_edit_in_progress:
                controller.end_interactive_edit()

    def test_begin_interactive_edit_bumps_prewarm_generation(self) -> None:
        from pyre.controllers.transformcontroller import TransformController

        controller = TransformController(_identity_mesh())
        gen_before = controller._rbf_prewarm_generation
        controller.begin_interactive_edit(Space.Target)
        try:
            self.assertGreater(controller._rbf_prewarm_generation, gen_before)
        finally:
            controller.end_interactive_edit()

    def test_rbf_prewarm_install_posts_to_gui_not_qtimer(self) -> None:
        from pyre.controllers.transformcontroller import TransformController

        mesh = _identity_mesh()
        captured: list = []

        def _capture_task(_name, func, *args, **kwargs):
            captured.append(func)
            return MagicMock()

        pool = MagicMock()
        pool.add_task.side_effect = _capture_task
        with patch("pyre.controllers.transformcontroller.GetTransformPrewarmPool", return_value=pool):
            controller = TransformController(mesh)
            self.assertTrue(captured)
            with patch("pyre.controllers.transformcontroller.QApplication") as qapp:
                qapp.instance.return_value = MagicMock()
                with patch("pyre.controllers.transformcontroller.QTimer") as timer:
                    with patch("pyre.controllers.transformcontroller.qt_post_to_main") as post:
                        captured[-1]()
        post.assert_called()
        timer.singleShot.assert_not_called()
        self.assertTrue(callable(post.call_args.args[0]))

    def test_rbf_prewarm_install_notifies_views(self) -> None:
        from pyre.controllers.transformcontroller import TransformController

        mesh = _identity_mesh()
        captured: list = []

        def _capture_task(_name, func, *args, **kwargs):
            captured.append(func)
            return MagicMock()

        pool = MagicMock()
        pool.add_task.side_effect = _capture_task
        with patch("pyre.controllers.transformcontroller.GetTransformPrewarmPool", return_value=pool):
            controller = TransformController(mesh)
            self.assertTrue(captured)
            with patch.object(controller, "notify_views_now") as notify:
                captured[-1]()
            notify.assert_called()
        self.assertIsNotNone(mesh._ForwardRBFInstance)
        self.assertTrue(controller._rbf_prewarm_ready)

    def test_stale_mesh_prewarm_install_is_discarded(self) -> None:
        from nornir_imageregistration.transforms.meshwithrbffallback import GetTransformPrewarmPool
        from pyre.controllers.transformcontroller import TransformController

        mesh = _identity_mesh()
        mesh.InitializeDataStructures()
        controller = TransformController(mesh)
        GetTransformPrewarmPool().wait_completion()
        live_rbf = mesh._ForwardRBFInstance
        captured: list = []

        def _capture_task(name, func, *args, **kwargs):
            captured.append(func)
            return MagicMock()

        controller.begin_interactive_edit(Space.Target)
        try:
            mesh.UpdateTargetPointsByIndex(
                0, np.asarray(mesh.TargetPoints[0], dtype=np.float64) + np.array((3.0, 1.0)))
            self.assertIs(mesh._ForwardRBFInstance, live_rbf)
            self.assertTrue(mesh._continuous_stale)
            with patch("pyre.controllers.transformcontroller.GetTransformPrewarmPool") as get_pool:
                pool = MagicMock()
                pool.add_task.side_effect = _capture_task
                get_pool.return_value = pool
                controller._queue_rbf_prewarm()
            self.assertTrue(captured)
            controller._rbf_prewarm_generation += 1
            captured[-1]()
            self.assertIs(mesh._ForwardRBFInstance, live_rbf)
            self.assertTrue(mesh._continuous_stale)
        finally:
            with patch.object(controller, "_queue_rbf_prewarm"):
                controller.end_interactive_edit()

    def test_interactive_transform_ignores_extrapolate_true(self) -> None:
        from pyre.controllers.transformcontroller import TransformController

        mesh = _identity_mesh()
        _ = mesh.source_space_trianglulation
        controller = TransformController(mesh)
        controller.begin_interactive_edit(Space.Target)
        try:
            mesh.UpdateTargetPointsByIndex(
                0, np.asarray(mesh.TargetPoints[0], dtype=np.float64) + np.array((3.0, 1.0)))
            self.assertIsNone(mesh._ForwardRBFInstance)
            with patch(
                    "nornir_imageregistration.transforms.meshwithrbffallback.OneWayRBFWithLinearCorrection",
                    side_effect=AssertionError("RBF")):
                controller.Transform(
                    np.asarray(mesh.SourcePoints), extrapolate=True)
        finally:
            with patch.object(controller, "_queue_rbf_prewarm"):
                controller.end_interactive_edit()

    def test_interactive_transform_does_not_construct_rbf_when_stale_exists(self) -> None:
        from pyre.controllers.transformcontroller import TransformController

        mesh = _identity_mesh()
        mesh.InitializeDataStructures()
        live_rbf = mesh._ForwardRBFInstance
        controller = TransformController(mesh)
        controller.begin_interactive_edit(Space.Target)
        try:
            mesh.UpdateTargetPointsByIndex(
                0, np.asarray(mesh.TargetPoints[0], dtype=np.float64) + np.array((3.0, 1.0)))
            self.assertIs(mesh._ForwardRBFInstance, live_rbf)
            with patch(
                    "nornir_imageregistration.transforms.meshwithrbffallback.OneWayRBFWithLinearCorrection",
                    side_effect=AssertionError("RBF")):
                controller.Transform(
                    np.asarray(mesh.SourcePoints), extrapolate=True)
            self.assertIs(mesh._ForwardRBFInstance, live_rbf)
        finally:
            with patch.object(controller, "_queue_rbf_prewarm"):
                controller.end_interactive_edit()

    def test_mesh_build_attaches_barycentric_stencil(self) -> None:
        transform = _identity_mesh()
        entry = gltiles.build_tile_mesh_cpu(
            transform, (0, 0), (32, 32), Space.Source, extrapolate=False)
        self.assertFalse(entry.is_rigid_quad)
        self.assertIsNotNone(entry.cp_indices)
        self.assertIsNotNone(entry.cp_weights)
        assert entry.cp_indices is not None
        assert entry.cp_weights is not None
        self.assertEqual(entry.cp_indices.shape, (entry.vertices.shape[0], 3))
        self.assertEqual(entry.cp_weights.shape, entry.cp_indices.shape)

    def test_grid_build_does_not_attach_mesh_stencil(self) -> None:
        entry = gltiles.build_tile_mesh_cpu(
            _identity_grid(), (0, 0), (32, 32), Space.Source)
        self.assertIsNone(entry.cp_indices)
        self.assertIsNone(entry.cp_weights)

    def test_second_target_stencil_patch_does_not_call_find_simplex(self) -> None:
        transform = _identity_mesh()
        source = np.asarray(transform.SourcePoints, dtype=np.float64)
        target = np.asarray(transform.TargetPoints, dtype=np.float64)
        delaunay = transform.source_space_trianglulation
        queries = np.array([[8.0, 8.0], [16.0, 16.0], [0.0, 0.0]], dtype=np.float64)
        cp_indices, cp_weights = barycentric_stencil_delaunay(queries, delaunay)
        mapped = apply_barycentric_stencil(cp_indices, cp_weights, target)
        verts = _pack_tile_vertices(mapped, queries)
        transform.UpdateTargetPointsByIndex(
            0, target[0] + np.array((4.0, -2.0), dtype=np.float64))
        first = gltiles.patch_tile_vertices_from_stencil(
            verts, cp_indices, cp_weights, transform.TargetPoints, transform.SourcePoints,
            np.array([0], dtype=np.intp), Space.Target)
        self.assertIsNotNone(first)
        assert first is not None
        with patch.object(delaunay, "find_simplex", side_effect=AssertionError("find_simplex")):
            second = gltiles.patch_tile_vertices_from_stencil(
                first[0], cp_indices, first[1], transform.TargetPoints, transform.SourcePoints,
                np.array([0], dtype=np.intp), Space.Target)
        self.assertIsNotNone(second)
        assert second is not None
        expected = apply_barycentric_stencil(
            cp_indices, cp_weights, np.asarray(transform.TargetPoints, dtype=np.float64))
        np.testing.assert_allclose(
            np.column_stack((second[0][:, 1], second[0][:, 0])),
            expected,
            rtol=1e-6,
            atol=1e-5,
        )

    @example(dy=0.0, dx=0.0)
    @example(dy=5.0, dx=-3.0)
    @given(
        dy=st.floats(-8.0, 8.0, allow_nan=False, allow_infinity=False),
        dx=st.floats(-8.0, 8.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=20, deadline=None)
    def test_target_stencil_patch_matches_barycentric_sample(self, dy: float, dx: float) -> None:
        transform = _identity_mesh()
        queries = np.array([[8.0, 8.0], [16.0, 16.0], [24.0, 8.0]], dtype=np.float64)
        delaunay = transform.source_space_trianglulation
        cp_indices, cp_weights = barycentric_stencil_delaunay(queries, delaunay)
        mapped = apply_barycentric_stencil(
            cp_indices, cp_weights, np.asarray(transform.TargetPoints, dtype=np.float64))
        verts = _pack_tile_vertices(mapped, queries)
        transform.UpdateTargetPointsByIndex(
            0, np.asarray(transform.TargetPoints[0], dtype=np.float64) + np.array((dy, dx)))
        patched = gltiles.patch_tile_vertices_from_stencil(
            verts, cp_indices, cp_weights, transform.TargetPoints, transform.SourcePoints,
            np.array([0], dtype=np.intp), Space.Target)
        self.assertIsNotNone(patched)
        assert patched is not None
        sampled = barycentric_sample_delaunay(
            queries, delaunay, np.asarray(transform.TargetPoints, dtype=np.float64))
        np.testing.assert_allclose(
            np.column_stack((patched[0][:, 1], patched[0][:, 0])),
            sampled,
            rtol=1e-6,
            atol=1e-5,
        )

    def test_source_stencil_patch_restencils_still_inside_without_find_simplex(self) -> None:
        transform = _identity_mesh()
        query = np.array([[8.0, 8.0]], dtype=np.float64)
        delaunay = transform.source_space_trianglulation
        cp_indices, cp_weights = barycentric_stencil_delaunay(query, delaunay)
        mapped = apply_barycentric_stencil(
            cp_indices, cp_weights, np.asarray(transform.TargetPoints, dtype=np.float64))
        verts = _pack_tile_vertices(mapped, query)
        from nornir_imageregistration import interactive_edit
        interactive_edit.begin()
        try:
            transform.UpdateSourcePointsByIndex(
                0, np.asarray(transform.SourcePoints[0], dtype=np.float64) + np.array((0.5, 0.4)))
            with patch.object(delaunay, "find_simplex", side_effect=AssertionError("find_simplex")):
                patched = gltiles.patch_tile_vertices_from_stencil(
                    verts, cp_indices, cp_weights, transform.TargetPoints, transform.SourcePoints,
                    np.array([0], dtype=np.intp), Space.Source)
            self.assertIsNotNone(patched)
            assert patched is not None
            self.assertFalse(np.allclose(patched[1], cp_weights))
            i0, i1, i2 = (int(v) for v in cp_indices[0])
            source = np.asarray(transform.SourcePoints, dtype=np.float64)
            expected_w, inside = barycentric_weights_in_triangle(
                query, source[i0], source[i1], source[i2])
            self.assertTrue(bool(inside[0]))
            np.testing.assert_allclose(patched[1], expected_w, rtol=1e-9, atol=1e-9)
        finally:
            interactive_edit.end()

    def test_source_stencil_patch_skips_vert_that_left_triangle_without_qhull(self) -> None:
        transform = _identity_mesh()
        query = np.array([[8.0, 8.0]], dtype=np.float64)
        delaunay = transform.source_space_trianglulation
        cp_indices, cp_weights = barycentric_stencil_delaunay(query, delaunay)
        mapped = apply_barycentric_stencil(
            cp_indices, cp_weights, np.asarray(transform.TargetPoints, dtype=np.float64))
        verts = _pack_tile_vertices(mapped, query)
        from nornir_imageregistration import interactive_edit
        interactive_edit.begin()
        try:
            transform.UpdateSourcePointsByIndex(0, np.array([30.0, 30.0], dtype=np.float64))
            with patch("scipy.spatial.Delaunay", side_effect=AssertionError("Qhull")):
                with patch.object(delaunay, "find_simplex", side_effect=AssertionError("find_simplex")):
                    patched = gltiles.patch_tile_vertices_from_stencil(
                        verts, cp_indices, cp_weights, transform.TargetPoints,
                        transform.SourcePoints, np.array([0], dtype=np.intp), Space.Source)
            self.assertIsNotNone(patched)
            assert patched is not None
            np.testing.assert_allclose(patched[0][:, 0:2], verts[:, 0:2])
            np.testing.assert_allclose(patched[1], cp_weights)
        finally:
            interactive_edit.end()

    def test_interactive_mesh_update_skips_tile_without_stencil(self) -> None:
        from pyre.views.imagetransformview import ImageTransformView

        transform = _identity_mesh()
        view = ImageTransformView.__new__(ImageTransformView)
        view._transform_controller = MagicMock()
        view._transform_controller.interactive_edit_in_progress = True
        view._transform_controller.interactive_edit_space = Space.Target
        view._transform_controller.tile_mesh_cache = TileMeshCpuCache()
        view._image_space = Space.Source
        view._warp_into_target_display = True
        view._image_viewmodel = MagicMock()
        view._image_viewmodel.TextureSize = np.array([64, 64], dtype=np.int32)
        view._image_viewmodel.width = 32
        view._image_viewmodel.height = 32
        view._activate_context = MagicMock()
        render_data = MagicMock()
        render_data.is_rigid_quad = False
        render_data.mesh_populated = True
        render_data.cp_indices = None
        render_data.cp_weights = None
        render_data.vertex_buffer.data = _pack_tile_vertices(
            np.asarray(transform.TargetPoints), np.asarray(transform.SourcePoints))
        view._tile_render_data = {(0, 0): render_data}
        with patch.object(ImageTransformView, "transform", new_callable=lambda: property(lambda self: transform)):
            with patch("pyre.views.gltiles._update_tile_buffers") as remesh:
                with patch("pyre.views.gltiles.source_to_target_mapper_for_interactive_drag") as mapper:
                    view.update_tiles_for_point_indices(np.array([0], dtype=np.intp))
        remesh.assert_not_called()
        mapper.assert_not_called()

    def test_source_patch_updates_nearest_neighbor_outside_hull_vert(self) -> None:
        """Outside-hull (i,i,i) stencils must still follow the moved control point."""
        query = np.array([[-8.0, -8.0]], dtype=np.float64)
        cp_indices = np.array([[0, 0, 0]], dtype=np.intp)
        cp_weights = np.array([[1.0, 0.0, 0.0]], dtype=np.float64)
        transform = _identity_mesh()
        mapped = np.asarray(transform.TargetPoints[0:1], dtype=np.float64)
        verts = _pack_tile_vertices(mapped, query)
        new_target = mapped[0] + np.array((4.0, -2.0), dtype=np.float64)
        transform.UpdateTargetPointsByIndex(0, new_target)
        patched = gltiles.patch_tile_vertices_from_stencil(
            verts, cp_indices, cp_weights, transform.TargetPoints, transform.SourcePoints,
            np.array([0], dtype=np.intp), Space.Source)
        self.assertIsNotNone(patched)
        assert patched is not None
        np.testing.assert_allclose(
            np.column_stack((patched[0][:, 1], patched[0][:, 0])),
            np.asarray([new_target], dtype=np.float64),
            rtol=1e-6,
            atol=1e-5,
        )


if __name__ == "__main__":
    unittest.main()
