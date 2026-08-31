"""Unit tests for transform display strategies and edit policy."""

from __future__ import annotations

import unittest

import numpy as np

import nornir_imageregistration
from nornir_imageregistration.transforms.transform_type import TransformType

from pyre.controllers.transform_display import (
    MeshLikeDisplayStrategy,
    RigidDisplayStrategy,
    TileRefreshHint,
    TransformDisplayStrategyRegistry,
    TransformGesture,
    display_strategy_for_model,
    gesture_for_interactive_edit,
    gesture_for_wheel_rotate,
)
from pyre.gl_engine.shaders.texture_shader import TextureShader
from pyre.interfaces.viewtype import ViewType
from pyre.space import Space
from pyre.transform_edit_policy import (
    control_point_translate_allowed,
    rigid_rotation_locked,
    wheel_rotate_locked,
)


class TestTransformDisplayRegistry(unittest.TestCase):
    """Strategy registry returns expected implementations per transform type."""

    def test_rigid_model_uses_rigid_strategy(self) -> None:
        model = nornir_imageregistration.transforms.CenteredSimilarity2DTransform(
            target_offset=(0, 0),
            source_rotation_center=(0, 0),
            angle=0,
            scalar=1,
        )
        strategy = display_strategy_for_model(model)
        self.assertIsInstance(strategy, RigidDisplayStrategy)
        self.assertTrue(strategy.uses_static_tile_quads())

    def test_registry_mesh_grid_rbf(self) -> None:
        registry = TransformDisplayStrategyRegistry()
        for transform_type in (TransformType.MESH, TransformType.GRID, TransformType.RBF):
            strategy = registry.for_model(type("M", (), {"type": transform_type})())  # type: ignore[arg-type]
            self.assertIsInstance(strategy, MeshLikeDisplayStrategy)
            self.assertFalse(strategy.uses_static_tile_quads())


class TestRigidDisplayStrategy(unittest.TestCase):
    """Rigid draw state follows registration model (model-authoritative)."""

    def setUp(self) -> None:
        self.strategy = RigidDisplayStrategy()
        self.model = nornir_imageregistration.transforms.CenteredSimilarity2DTransform(
            target_offset=(10.0, 5.0),
            source_rotation_center=(0, 0),
            angle=0.2,
            scalar=1,
        )

    def test_resolve_draw_state_matches_shader_helper(self) -> None:
        state = self.strategy.resolve_draw_state(
            image_space=Space.Source,
            view_type=ViewType.Composite,
            composite_fixed_align=True,
            model=self.model,
            tween=1.0,
            interactive_edit_in_progress=False,
            edit_space=None,
        )
        expected_fwd, expected_inv = TextureShader.rigid_matrices_from_transform(self.model)
        np.testing.assert_allclose(state.source_to_target, expected_fwd)
        np.testing.assert_allclose(state.target_to_source, expected_inv)
        self.assertTrue(state.use_rigid_path)
        self.assertIsNotNone(state.rigid_overlay)
        np.testing.assert_allclose(
            state.rigid_overlay.fixed_display_matrix, np.eye(3, dtype=np.float32))

    def test_warped_frozen_during_composite_source_edit(self) -> None:
        self.strategy.begin_gesture(TransformGesture.COMPOSITE_TRANSLATE, Space.Source)
        self.strategy.snapshot_edit_matrices(self.model)
        frozen_fwd = self.strategy.matrix_at_edit_start.copy()
        self.model.TranslateFixed((3.0, 2.0))
        state = self.strategy.resolve_draw_state(
            image_space=Space.Target,
            view_type=ViewType.Composite,
            composite_fixed_align=False,
            model=self.model,
            tween=1.0,
            interactive_edit_in_progress=True,
            edit_space=Space.Source,
        )
        np.testing.assert_allclose(state.source_to_target, frozen_fwd)

    def test_gesture_mode_cleared_on_end(self) -> None:
        self.strategy.begin_gesture(TransformGesture.COMPOSITE_ROTATE, Space.Source)
        self.strategy.end_gesture()
        self.assertEqual(self.strategy.gesture, TransformGesture.NONE)


class TestGestureMapping(unittest.TestCase):
    """Gesture helpers map spaces and views to enum values."""

    def test_composite_translate_gesture(self) -> None:
        gesture = gesture_for_interactive_edit(
            Space.Source, ViewType.Composite, TransformType.RIGID)
        self.assertEqual(gesture, TransformGesture.COMPOSITE_TRANSLATE)

    def test_composite_rotate_on_wheel(self) -> None:
        gesture = gesture_for_wheel_rotate(
            Space.Source, ViewType.Composite, TransformType.RIGID)
        self.assertEqual(gesture, TransformGesture.COMPOSITE_ROTATE)


class TestTransformEditPolicy(unittest.TestCase):
    """Expanded gesture policy matrix."""

    def test_rigid_rotation_only_in_composite(self) -> None:
        self.assertFalse(rigid_rotation_locked(TransformType.RIGID, ViewType.Composite))
        self.assertTrue(rigid_rotation_locked(TransformType.RIGID, ViewType.Target))

    def test_wheel_rotate_locked_on_fixed_panel(self) -> None:
        self.assertTrue(wheel_rotate_locked(
            TransformType.RIGID, Space.Source, ViewType.Source))

    def test_mesh_control_point_translate(self) -> None:
        self.assertTrue(control_point_translate_allowed(TransformType.MESH, Space.Target))


class TestMeshLikeStrategy(unittest.TestCase):
    """Mesh-like strategies preserve incremental refresh hints."""

    def test_point_moved_is_incremental(self) -> None:
        strategy = MeshLikeDisplayStrategy(TransformType.MESH)
        self.assertEqual(strategy.on_point_moved([0, 1]), TileRefreshHint.INCREMENTAL)


if __name__ == "__main__":
    unittest.main()
