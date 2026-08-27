"""Tests that cancelling a rigid drag actually undoes it.

The command captured ``transform_controller.TransformModel`` itself rather than
a snapshot of its parameters. Translate mutates that model in place, so cancel
reassigned the already-mutated object and the misalignment was committed
silently.
"""

from __future__ import annotations

import unittest

import numpy as np

from nornir_imageregistration import EnsureNumpyArray, IRigidTransform
from nornir_imageregistration.transforms import CenteredSimilarity2DTransform, Rigid

from pyre.commands.stos.translaterigidcommand import ManipulateRigidTransformCommand
from pyre.controllers.transformcontroller import TransformController
from pyre.space import Space


def _command_for(controller: TransformController) -> ManipulateRigidTransformCommand:
    """Build the command without the Qt/DI machinery, as tests/test_rigid_gestures does."""
    cmd = object.__new__(ManipulateRigidTransformCommand)
    cmd._transform_controller = controller
    cmd._space = Space.Source
    cmd._translate_origin = None
    # Mirrors what __init__ records.
    model = controller.TransformModel
    assert isinstance(model, IRigidTransform)
    cmd._original_state = model.GetRigidState()
    return cmd


class TestRigidDragCancelRestoresTransform(unittest.TestCase):
    """A cancelled drag must leave the registration exactly where it started."""

    def setUp(self) -> None:
        self.controller = TransformController(
            Rigid(target_offset=(10.0, 20.0),
                  source_rotation_center=(0.0, 0.0),
                  angle=0.0))
        # The controller promotes a plain Rigid to CenteredSimilarity2DTransform,
        # so the shared instance is the one it holds, not the one passed in.
        self.model = self.controller.TransformModel
        self.probe = np.array([[0.0, 0.0], [100.0, 50.0]])
        self.before = np.array(
            EnsureNumpyArray(self.controller.Transform(self.probe)), copy=True)
        self.cmd = _command_for(self.controller)

    def test_cancel_undoes_a_translate(self):
        self.controller.Translate(np.array([37.0, -19.0]), space=Space.Source)
        self.assertFalse(np.allclose(
            EnsureNumpyArray(self.controller.Transform(self.probe)), self.before),
            'the drag should have moved the transform')

        self.cmd._restore_original_state()

        np.testing.assert_allclose(
            EnsureNumpyArray(self.controller.Transform(self.probe)),
            self.before, atol=1e-5)

    def test_cancel_undoes_a_multi_step_drag(self):
        """A real drag applies many small deltas."""
        for _ in range(25):
            self.controller.Translate(np.array([2.0, 1.0]), space=Space.Source)

        self.cmd._restore_original_state()

        np.testing.assert_allclose(
            EnsureNumpyArray(self.controller.Transform(self.probe)),
            self.before, atol=1e-5)

    def test_cancel_keeps_the_shared_model_instance(self):
        """All STOS views hold this object; swapping it would strand them."""
        self.controller.Translate(np.array([5.0, 5.0]), space=Space.Source)

        self.cmd._restore_original_state()

        self.assertIs(self.controller.TransformModel, self.model)

    def test_cancel_notifies_views(self):
        calls: list[int] = []
        self.model.AddOnChangeEventListener(  # type: ignore[attr-defined]
            lambda *a, **k: calls.append(1))
        self.controller.Translate(np.array([5.0, 5.0]), space=Space.Source)
        calls.clear()

        self.cmd._restore_original_state()

        self.assertTrue(calls, 'panels would keep drawing the cancelled position')

    def test_snapshot_is_not_a_live_reference(self):
        """The captured state must not track later mutation."""
        captured = dict(self.cmd._original_state)
        self.controller.Translate(np.array([50.0, 50.0]), space=Space.Source)

        np.testing.assert_allclose(self.cmd._original_state['target_offset'],
                                   captured['target_offset'])


class TestRigidDragCancelWithScale(unittest.TestCase):
    """Shift+scroll relative scale has to be undone too."""

    def test_cancel_undoes_scale_and_translate(self):
        model = CenteredSimilarity2DTransform(target_offset=(4.0, 6.0),
                                              source_rotation_center=(1.0, 1.0),
                                              angle=0.05)
        controller = TransformController(model)
        probe = np.array([[10.0, 10.0], [-20.0, 30.0]])
        before = np.array(EnsureNumpyArray(controller.Transform(probe)), copy=True)
        cmd = _command_for(controller)

        controller.Translate(np.array([15.0, 15.0]), space=Space.Source)
        model.ScaleWarped(1.4)

        cmd._restore_original_state()

        np.testing.assert_allclose(EnsureNumpyArray(controller.Transform(probe)),
                                   before, atol=1e-4)


if __name__ == '__main__':
    unittest.main()
