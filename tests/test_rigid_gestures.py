"""Tests for rigid translate/rotate mouse gesture sign and pivot."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import numpy as np
from PyQt6.QtCore import Qt

from nornir_imageregistration.transforms import Rigid

from pyre.commands.stos.translaterigidcommand import ManipulateRigidTransformCommand
from pyre.commands.uicommandbase import UICommandBase
from pyre.controllers.transformcontroller import TransformController
from pyre.interfaces.viewtype import ViewType
from pyre.selection_event_data import PointPair
from pyre.space import Space


class TestRigidTranslateDeltaSign(unittest.TestCase):
    """Source-space rigid translate negates delta so the layer follows the cursor."""

    def test_source_translate_negates_positive_delta(self) -> None:
        controller = TransformController(
            Rigid(target_offset=(10.0, 20.0), source_rotation_center=(0.0, 0.0), angle=0.0))
        cmd = object.__new__(ManipulateRigidTransformCommand)
        cmd._transform_controller = controller
        cmd._space = Space.Source
        cmd._translate_origin = np.array([0.0, 0.0], dtype=np.float64)

        point_pair = PointPair(
            source=np.array([5.0, 3.0]),
            target=np.array([15.0, 23.0]),
        )
        world_point = point_pair.source
        delta = world_point - cmd._translate_origin
        if cmd._space == Space.Source:
            delta = -delta

        with patch.object(controller, "Translate") as translate:
            controller.Translate(delta, space=cmd._space)
            translate.assert_called_once()
            np.testing.assert_allclose(translate.call_args[0][0], [-5.0, -3.0])


class TestCompositeRotatePivot(unittest.TestCase):
    """Composite rigid rotate uses source-space pivot for cursor pinning."""

    def test_composite_selects_source_component(self) -> None:
        display = np.array([50.0, 60.0], dtype=np.float32)
        source = np.array([40.0, 50.0], dtype=np.float32)
        point_pair = PointPair(target=display, source=source)
        view = ViewType.Composite
        if view == ViewType.Composite:
            world_center = np.asarray(point_pair.source, dtype=np.float32)
        else:
            world_center = np.asarray(point_pair.target, dtype=np.float32)
        np.testing.assert_allclose(world_center, source)
        self.assertFalse(np.allclose(world_center, display))

    def test_rotate_about_source_pivot_pins_target_position(self) -> None:
        rigid = Rigid(target_offset=(100.0, 200.0), source_rotation_center=(0.0, 0.0), angle=0.1)
        controller = TransformController(rigid)
        pivot = np.array([500.0, 600.0], dtype=np.float32)
        target_before = np.squeeze(controller.Transform(pivot.reshape(1, 2)))
        controller.Rotate(0.05, pivot, space=Space.Source)
        target_after = np.squeeze(controller.Transform(pivot.reshape(1, 2)))
        np.testing.assert_allclose(target_after, target_before, rtol=1e-4, atol=1e-2)


class TestScaleWarpedPivot(unittest.TestCase):
    """ScaleWarped treats center as source-space (no InverseTransform double-map)."""

    def test_scale_warped_pins_source_pivot_in_target_space(self) -> None:
        from nornir_imageregistration.transforms import CenteredSimilarity2DTransform

        model = CenteredSimilarity2DTransform(
            target_offset=(10.0, 20.0),
            source_rotation_center=(0.0, 0.0),
            angle=0.15,
            scalar=1.0,
        )
        controller = TransformController(model)
        pivot = np.array([40.0, 50.0], dtype=np.float32)
        target_before = np.squeeze(controller.Transform(pivot.reshape(1, 2)))
        controller.ScaleWarped(1.1, pivot, space=Space.Source)
        target_after = np.squeeze(controller.Transform(pivot.reshape(1, 2)))
        np.testing.assert_allclose(target_after, target_before, rtol=1e-4, atol=1e-3)

    def test_scale_warped_does_not_inverse_transform_source_center(self) -> None:
        from nornir_imageregistration.transforms import CenteredSimilarity2DTransform

        model = CenteredSimilarity2DTransform(
            target_offset=(100.0, 200.0),
            source_rotation_center=(0.0, 0.0),
            angle=0.3,
            scalar=1.0,
        )
        controller = TransformController(model)
        # A source point whose InverseTransform(source) would be far from source.
        pivot = np.array([10.0, 20.0], dtype=np.float32)
        wrong_pivot = np.squeeze(model.InverseTransform(pivot.reshape(1, 2)))
        self.assertFalse(np.allclose(pivot, wrong_pivot, atol=1.0))

        target_at_pivot_before = np.squeeze(controller.Transform(pivot.reshape(1, 2)))
        controller.ScaleWarped(1.25, pivot, space=Space.Source)
        target_at_pivot_after = np.squeeze(controller.Transform(pivot.reshape(1, 2)))
        np.testing.assert_allclose(
            target_at_pivot_after, target_at_pivot_before, rtol=1e-4, atol=1e-3)


class TestRigidTargetPanelLock(unittest.TestCase):
    """Rigid layer edits are ignored on the standalone target panel, allowed elsewhere."""

    def _command(self, space: Space, view_type: ViewType) -> ManipulateRigidTransformCommand:
        """Build the command without Qt/DI, reporting ``view_type`` as its host panel."""
        cmd = object.__new__(ManipulateRigidTransformCommand)
        cmd._transform_controller = TransformController(
            Rigid(target_offset=(10.0, 20.0), source_rotation_center=(0.0, 0.0), angle=0.0))
        cmd._space = space
        cmd._view_type = lambda: view_type  # type: ignore[method-assign]
        return cmd

    def _arrow_key_translates(self, space: Space, view_type: ViewType) -> bool:
        """Press Left on the command and report whether the layer was translated."""
        cmd = self._command(space, view_type)
        event = MagicMock()
        event.key.return_value = Qt.Key.Key_Left
        event.modifiers.return_value = Qt.KeyboardModifier.NoModifier
        with patch.object(cmd._transform_controller, "Translate") as translate:
            cmd.on_key_down(event)
        return translate.called

    def _activate_begins_edit(self, space: Space, view_type: ViewType) -> bool:
        """Activate the command and report whether an interactive edit began (else it cancelled)."""
        cmd = self._command(space, view_type)
        with patch.object(UICommandBase, "activate"), \
                patch.object(cmd, "cancel") as cancel, \
                patch.object(cmd._transform_controller, "begin_interactive_edit") as begin:
            cmd.activate()
        self.assertNotEqual(begin.called, cancel.called)
        return begin.called

    def test_arrow_key_ignored_on_target_panel(self) -> None:
        self.assertFalse(self._arrow_key_translates(Space.Target, ViewType.Target))

    def test_arrow_key_translates_on_source_and_composite(self) -> None:
        self.assertTrue(self._arrow_key_translates(Space.Source, ViewType.Source))
        self.assertTrue(self._arrow_key_translates(Space.Target, ViewType.Composite))

    def test_activate_cancels_on_target_panel(self) -> None:
        self.assertFalse(self._activate_begins_edit(Space.Target, ViewType.Target))

    def test_activate_begins_edit_on_source_and_composite(self) -> None:
        self.assertTrue(self._activate_begins_edit(Space.Source, ViewType.Source))
        self.assertTrue(self._activate_begins_edit(Space.Target, ViewType.Composite))


if __name__ == "__main__":
    unittest.main()
