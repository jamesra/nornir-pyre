"""Tests for Pyre panel space vs registration control-point column mapping."""

from __future__ import annotations

import copy
import unittest
from unittest.mock import MagicMock, patch

import numpy as np
from hypothesis import example, given, settings
from hypothesis import strategies as st

import nornir_imageregistration
from nornir_imageregistration.grid_subdivision import ITKGridDivision
from nornir_imageregistration.transforms import CenteredSimilarity2DTransform
from nornir_imageregistration.transforms.gridtransform import GridTransform
from nornir_imageregistration.transforms.meshwithrbffallback import MeshWithRBFFallback

from pyre.commands.navigationcommandbase import wheel_scale_uses_target_points
from pyre.commands.stos.point_coords import known_space_for_control_point_create
from pyre.commands.stos.translatecontrolpointcommand import TranslateControlPointCommand
from pyre.controllers.transformcontroller import TransformController
from pyre.interfaces.viewtype import ViewType
from pyre.space import Space
from pyre.viewmodels.controlpointmap import ControlPointMap
from pyre.views.composite_display import composite_control_point_draw_rows


def _mesh_with_offset() -> MeshWithRBFFallback:
    """Four-point mesh with distinct target and source coordinates."""
    points = np.array([
        [10.0, 20.0, 100.0, 200.0],
        [30.0, 40.0, 300.0, 400.0],
        [50.0, 60.0, 500.0, 600.0],
        [70.0, 80.0, 700.0, 800.0],
    ], dtype=np.float32)
    return MeshWithRBFFallback(points)


def _identity_grid() -> GridTransform:
    """Small grid with aligned source/target points."""
    from nornir_imageregistration.transforms import Rigid

    grid = ITKGridDivision(source_shape=(32, 32), cell_size=(16, 16))
    grid.PopulateTargetPoints(
        Rigid(target_offset=(0.0, 0.0), source_rotation_center=(16.0, 16.0), angle=0.0))
    return GridTransform(grid)


class TestControlPointSpaceMapping(unittest.TestCase):
    """MovePoint/GetPoints/ControlPointMap align Pyre Space with registration columns."""

    def setUp(self) -> None:
        self.controller = TransformController(_mesh_with_offset())

    def test_get_points_source_returns_source_columns(self) -> None:
        source = self.controller.GetPoints(0, space=Space.Source)
        np.testing.assert_allclose(source, [100.0, 200.0])

    def test_get_points_target_returns_target_columns(self) -> None:
        target = self.controller.GetPoints(0, space=Space.Target)
        np.testing.assert_allclose(target, [10.0, 20.0])

    def test_move_point_source_updates_source_points_only(self) -> None:
        before = copy.deepcopy(self.controller.points)
        self.controller.MovePoint(0, ImageDX=2.0, ImageDY=1.0, space=Space.Source)
        after = self.controller.points
        np.testing.assert_allclose(after[0, 2:4], before[0, 2:4] + np.array([1.0, 2.0]))
        np.testing.assert_allclose(after[1:, 2:4], before[1:, 2:4])
        np.testing.assert_allclose(after[:, 0:2], before[:, 0:2])

    def test_move_point_target_updates_target_points_only(self) -> None:
        before = copy.deepcopy(self.controller.points)
        self.controller.MovePoint(1, ImageDX=-3.0, ImageDY=4.0, space=Space.Target)
        after = self.controller.points
        np.testing.assert_allclose(after[:, 2:4], before[:, 2:4])
        np.testing.assert_allclose(after[1, 0:2], before[1, 0:2] + np.array([4.0, -3.0]))
        np.testing.assert_allclose(after[0, 0:2], before[0, 0:2])
        np.testing.assert_allclose(after[2:, 0:2], before[2:, 0:2])

    def test_controlpointmap_source_uses_source_points(self) -> None:
        cmap = ControlPointMap(self.controller, Space.Source)
        np.testing.assert_allclose(cmap.points, self.controller.SourcePoints)

    def test_controlpointmap_target_uses_target_points(self) -> None:
        cmap = ControlPointMap(self.controller, Space.Target)
        np.testing.assert_allclose(cmap.points, self.controller.TargetPoints)

    def test_draw_tween_matches_hit_test_space(self) -> None:
        self.assertEqual(ControlPointMap.draw_tween_for_pyre_space(Space.Source), 0.0)
        self.assertEqual(ControlPointMap.draw_tween_for_pyre_space(Space.Target), 1.0)

    def test_shader_tween_draws_registration_columns(self) -> None:
        """Shader tween 0 selects SourcePoints; 1 selects TargetPoints."""
        source_tween = ControlPointMap.shader_tween_for_panel_space(Space.Source)
        target_tween = ControlPointMap.shader_tween_for_panel_space(Space.Target)
        self.assertEqual(source_tween, 0.0)
        self.assertEqual(target_tween, 1.0)
        cmap_source = ControlPointMap(self.controller, Space.Source)
        cmap_target = ControlPointMap(self.controller, Space.Target)
        np.testing.assert_allclose(cmap_source.points, self.controller.SourcePoints)
        np.testing.assert_allclose(cmap_target.points, self.controller.TargetPoints)


class TestGridControlPointDragDirection(unittest.TestCase):
    """Grid CP drags must move TargetPoints in the same direction as the mouse."""

    def test_grid_move_point_target_follows_positive_delta(self) -> None:
        controller = TransformController(_identity_grid())
        before = np.array(controller.TargetPoints[0], copy=True)
        controller.MovePoint(0, ImageDX=5.0, ImageDY=3.0, space=Space.Target)
        after = controller.TargetPoints[0]
        np.testing.assert_allclose(after, before + np.array([3.0, 5.0]))

    def test_grid_source_space_fallback_moves_target_same_direction(self) -> None:
        """Grid has no source-point edit; Source MovePoint maps into TargetPoints."""
        controller = TransformController(_identity_grid())
        before = np.array(controller.TargetPoints[0], copy=True)
        source_before = np.array(controller.SourcePoints[0], copy=True)
        # Positive ImageDX/ImageDY must move the editable target point +Y/+X, not invert.
        controller.MovePoint(0, ImageDX=5.0, ImageDY=3.0, space=Space.Source)
        after = controller.TargetPoints[0]
        np.testing.assert_allclose(after, before + np.array([3.0, 5.0]), atol=1e-3)
        np.testing.assert_allclose(controller.SourcePoints[0], source_before)

    def test_composite_translate_command_edits_target_space(self) -> None:
        cmd = object.__new__(TranslateControlPointCommand)
        cmd._space = Space.Source
        cmd._transform_controller = TransformController(_identity_grid())
        cmd._view_type = MagicMock(return_value=ViewType.Composite)  # type: ignore[method-assign]
        self.assertEqual(cmd._edit_space_for_translate(), Space.Target)

    def test_composite_activate_begins_interactive_edit_in_target_space(self) -> None:
        from pyre.commands.navigationcommandbase import NavigationCommandBase

        cmd = object.__new__(TranslateControlPointCommand)
        cmd._space = Space.Source
        controller = MagicMock()
        cmd._transform_controller = controller
        cmd._view_type = MagicMock(return_value=ViewType.Composite)  # type: ignore[method-assign]
        cmd._selected_point_set = set()
        cmd._command_points = {0}
        with patch.object(NavigationCommandBase, "activate", lambda self: None):
            TranslateControlPointCommand.activate(cmd)
        controller.begin_interactive_edit.assert_called_once_with(
            Space.Target, view_type=ViewType.Composite)


def _identity_mesh_square() -> MeshWithRBFFallback:
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


class TestKnownSpaceForCreate(unittest.TestCase):
    def test_composite_uses_target_display_coords(self) -> None:
        self.assertEqual(
            known_space_for_control_point_create(Space.Source, ViewType.Composite),
            Space.Target,
        )

    def test_source_and_target_views_keep_space(self) -> None:
        self.assertEqual(
            known_space_for_control_point_create(Space.Source, ViewType.Source),
            Space.Source,
        )
        self.assertEqual(
            known_space_for_control_point_create(Space.Target, ViewType.Target),
            Space.Target,
        )


class TestMapPairForControlPointCreate(unittest.TestCase):
    """Outside-hull create remaps through a stale RBF without rebuilding structures."""

    @example(y=-20.0, x=-20.0)
    @example(y=80.0, x=50.0)
    @given(
        y=st.floats(-40.0, -1.0, allow_nan=False, allow_infinity=False),
        x=st.floats(33.0, 80.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=20, deadline=None)
    def test_oob_source_click_finite_from_stale_rbf(self, y: float, x: float) -> None:
        mesh = _identity_mesh_square()
        mesh.InitializeDataStructures()
        live_rbf = mesh._ForwardRBFInstance
        with patch("pyre.controllers.transformcontroller.GetTransformPrewarmPool"):
            controller = TransformController(mesh)
            mesh.UpdateTargetPointsByIndex(
                0, np.asarray(mesh.TargetPoints[0], dtype=np.float64) + np.array((5.0, -3.0)))
            self.assertIs(mesh._ForwardRBFInstance, live_rbf)
            self.assertTrue(mesh._continuous_stale)
            with patch.object(
                    mesh, "InitializeDataStructures", side_effect=AssertionError("init")):
                pair = controller.map_pair_for_control_point_create(
                    Space.Source, np.array((y, x), dtype=np.float64))
        np.testing.assert_allclose(pair.source, np.array((y, x), dtype=np.float64))
        self.assertTrue(np.all(np.isfinite(pair.target)))
        self.assertIs(mesh._ForwardRBFInstance, live_rbf)

    def test_try_add_point_oob_does_not_initialize(self) -> None:
        mesh = _identity_mesh_square()
        mesh.InitializeDataStructures()
        live_rbf = mesh._ForwardRBFInstance
        n_before = int(mesh.points.shape[0])
        with patch("pyre.controllers.transformcontroller.GetTransformPrewarmPool"):
            controller = TransformController(mesh)
            mesh.UpdateTargetPointsByIndex(
                0, np.asarray(mesh.TargetPoints[0], dtype=np.float64) + np.array((4.0, 2.0)))
            with patch.object(
                    mesh, "InitializeDataStructures", side_effect=AssertionError("init")):
                controller.TryAddPoint(-20.0, -25.0, space=Space.Source)
        self.assertEqual(int(mesh.points.shape[0]), n_before + 1)
        added = np.asarray(mesh.points[-1], dtype=np.float64)
        self.assertTrue(np.all(np.isfinite(added)))
        np.testing.assert_allclose(added[2:4], np.array((-25.0, -20.0)))
        self.assertIs(mesh._ForwardRBFInstance, live_rbf)

    @unittest.skipUnless(nornir_imageregistration.HasCupy(), "requires CuPy")
    def test_map_pair_host_from_cupy_transform_output(self) -> None:
        """GPU mesh InverseTransform/Transform returns CuPy; create-point needs host YX."""
        import cupy as cp

        mesh = _identity_mesh_square()
        mesh.InitializeDataStructures()
        with patch("pyre.controllers.transformcontroller.GetTransformPrewarmPool"):
            controller = TransformController(mesh)
            with patch.object(
                    mesh, "InverseTransform",
                    return_value=cp.asarray([[3.0, 4.0]], dtype=cp.float64)):
                pair = controller.map_pair_for_control_point_create(
                    Space.Target, np.array((10.0, 20.0), dtype=np.float64))
            with patch.object(
                    mesh, "Transform",
                    return_value=cp.asarray([[5.0, 6.0]], dtype=cp.float64)):
                pair_src = controller.map_pair_for_control_point_create(
                    Space.Source, np.array((7.0, 8.0), dtype=np.float64))
        np.testing.assert_allclose(pair.target, [10.0, 20.0])
        np.testing.assert_allclose(pair.source, [3.0, 4.0])
        self.assertIsInstance(pair.source, np.ndarray)
        np.testing.assert_allclose(pair_src.source, [7.0, 8.0])
        np.testing.assert_allclose(pair_src.target, [5.0, 6.0])
        self.assertIsInstance(pair_src.target, np.ndarray)


def _non_collinear_mesh() -> MeshWithRBFFallback:
    """Four-point mesh with a 2D source/target hull (not a line)."""
    points = np.array([
        [10.0, 20.0, 100.0, 200.0],
        [10.0, 80.0, 100.0, 800.0],
        [70.0, 20.0, 700.0, 200.0],
        [70.0, 80.0, 700.0, 800.0],
    ], dtype=np.float64)
    return MeshWithRBFFallback(points)


class TestWheelScaleTargetPointsRouting(unittest.TestCase):
    """Composite/target mesh Shift+scroll scales TargetPoints; rigid stays ScaleWarped."""

    def test_composite_mesh_uses_target_points(self) -> None:
        self.assertTrue(wheel_scale_uses_target_points(
            _non_collinear_mesh(), ViewType.Composite, Space.Source))

    def test_source_panel_mesh_uses_source_points(self) -> None:
        self.assertFalse(wheel_scale_uses_target_points(
            _non_collinear_mesh(), ViewType.Source, Space.Source))

    def test_target_panel_mesh_uses_target_points(self) -> None:
        self.assertTrue(wheel_scale_uses_target_points(
            _non_collinear_mesh(), ViewType.Target, Space.Target))

    def test_composite_grid_uses_target_points(self) -> None:
        self.assertTrue(wheel_scale_uses_target_points(
            _identity_grid(), ViewType.Composite, Space.Source))

    def test_composite_rigid_does_not_use_target_points(self) -> None:
        rigid = CenteredSimilarity2DTransform(
            target_offset=(10.0, 20.0),
            source_rotation_center=(0.0, 0.0),
            angle=0.0,
            scalar=1.0,
        )
        self.assertFalse(wheel_scale_uses_target_points(
            rigid, ViewType.Composite, Space.Source))


class TestMeshScaleFixedAboutTargetPivot(unittest.TestCase):
    """Composite mesh scale must move TargetPoints, not SourcePoints."""

    def test_scale_fixed_leaves_source_points_unchanged(self) -> None:
        controller = TransformController(_non_collinear_mesh())
        source_before = np.array(controller.SourcePoints, copy=True)
        target_before = np.array(controller.TargetPoints, copy=True)
        pivot = np.array([40.0, 50.0], dtype=np.float64)
        controller.ScaleFixed(2.0, pivot, space=Space.Target)
        np.testing.assert_allclose(controller.SourcePoints, source_before)
        expected_target = (target_before - pivot) * 2.0 + pivot
        np.testing.assert_allclose(controller.TargetPoints, expected_target)

    def test_scale_fixed_pins_target_pivot(self) -> None:
        controller = TransformController(_non_collinear_mesh())
        pivot = np.array(controller.TargetPoints[0], copy=True)
        controller.ScaleFixed(1.5, pivot, space=Space.Target)
        np.testing.assert_allclose(controller.TargetPoints[0], pivot)

    def test_scale_fixed_updates_composite_draw_rows(self) -> None:
        controller = TransformController(_non_collinear_mesh())
        pivot = np.array([40.0, 50.0], dtype=np.float64)
        controller.ScaleFixed(2.0, pivot, space=Space.Target)
        rows = composite_control_point_draw_rows(controller, Space.Source)
        assert rows is not None
        np.testing.assert_allclose(rows[:, 0:2], controller.TargetPoints)
        np.testing.assert_allclose(rows[:, 2:4], controller.TargetPoints)

    @given(
        scale=st.floats(min_value=0.5, max_value=2.0, allow_nan=False, allow_infinity=False).filter(
            lambda s: abs(s - 1.0) > 0.05),
        py=st.floats(min_value=-20.0, max_value=120.0, allow_nan=False, allow_infinity=False),
        px=st.floats(min_value=-20.0, max_value=120.0, allow_nan=False, allow_infinity=False),
    )
    @example(scale=2.0, py=40.0, px=50.0)
    @settings(max_examples=40, deadline=None)
    def test_scale_fixed_about_arbitrary_pivot(self, scale: float, py: float, px: float) -> None:
        controller = TransformController(_non_collinear_mesh())
        source_before = np.array(controller.SourcePoints, copy=True)
        target_before = np.array(controller.TargetPoints, copy=True)
        pivot = np.array([py, px], dtype=np.float64)
        controller.ScaleFixed(scale, pivot, space=Space.Target)
        np.testing.assert_allclose(controller.SourcePoints, source_before)
        expected = (target_before - pivot) * scale + pivot
        np.testing.assert_allclose(controller.TargetPoints, expected, rtol=1e-5, atol=1e-5)
        mapped = np.asarray(controller.Transform(controller.SourcePoints))
        np.testing.assert_allclose(mapped, controller.TargetPoints, rtol=1e-4, atol=1e-3)


if __name__ == "__main__":
    unittest.main()
