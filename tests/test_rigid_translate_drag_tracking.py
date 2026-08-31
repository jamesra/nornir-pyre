"""Tests that a rigid translate drag tracks the mouse 1:1 in every STOS panel.

`ManipulateRigidTransformCommand.on_mouse_motion` re-derives the drag origin after
`Translate` has mutated the shared model. That looks redundant, but on the composite panel
the drag quantity lives in target-display space, which the mutation just moved under a
stationary cursor. Reusing the pre-mutation point there double-counts every step. These
tests pin the 1:1 invariant so the re-derivation is not "optimised" away.
"""

from __future__ import annotations

import unittest

import numpy as np
from nornir_imageregistration.transforms.rigid import CenteredSimilarity2DTransform

from pyre.commands.navigationcommandbase import NavigationCommandBase
from pyre.controllers.transformcontroller import TransformController
from pyre.interfaces.viewtype import ViewType
from pyre.space import Space

_PANEL_HEIGHT = 1000
_LOOKAT = 500.0


class _Camera:
    """Identity screen-to-image mapping, enough for composite display helpers."""

    def __init__(self) -> None:
        self.lookat = np.array([_LOOKAT, _LOOKAT], dtype=np.float64)

    def ImageCoordsForMouse(self, cy: float, cx: float) -> np.ndarray:
        return np.array([cy, cx], dtype=np.float64)

    def image_coords_for_lookat(self, lookat, cy: float, cx: float) -> np.ndarray:
        return np.asarray(lookat, dtype=np.float64) + np.array([cy - _LOOKAT, cx - _LOOKAT])


class _Harness:
    """The attributes get_world_positions touches, plus the motion arithmetic."""

    height = _PANEL_HEIGHT
    GetCorrectedMousePosition = staticmethod(NavigationCommandBase.GetCorrectedMousePosition)

    def __init__(self, controller: TransformController, space: Space,
                 view_type: ViewType) -> None:
        self.camera = _Camera()
        self._transform_controller = controller
        self._space = space
        self._view = view_type
        self._translate_origin: np.ndarray | None = None

    @property
    def space(self) -> Space:
        return self._space

    def _view_type(self) -> ViewType:
        return self._view

    def get_world_positions(self, event):
        return NavigationCommandBase.get_world_positions(self, event)

    def _world_point_for_translate(self, point_pair) -> np.ndarray:
        if self._view_type() == ViewType.Composite:
            return point_pair.target
        return point_pair.source if self.space == Space.Source else point_pair.target

    def motion(self, screen_yx: tuple[float, float], *, rederive: bool = True) -> None:
        """The body of on_mouse_motion, with the re-derivation switchable."""
        world_point = self._world_point_for_translate(self.get_world_positions(screen_yx))

        if self._translate_origin is None:
            self._translate_origin = world_point
            return

        delta = world_point - self._translate_origin
        if self.space == Space.Source:
            delta = -delta

        self._transform_controller.Translate(delta, space=self.space)

        if rederive:
            self._translate_origin = self._world_point_for_translate(
                self.get_world_positions(screen_yx))
        else:
            self._translate_origin = world_point


def _controller(angle: float = 0.0, scalar: float = 1.0) -> TransformController:
    return TransformController(CenteredSimilarity2DTransform(
        target_offset=(0.0, 0.0),
        source_rotation_center=(_LOOKAT, _LOOKAT),
        angle=angle,
        scalar=scalar))


_PATH = [(400.0, 600.0), (410.0, 600.0), (420.0, 610.0), (430.0, 625.0), (445.0, 640.0)]


def _screen_delta(path: list[tuple[float, float]]) -> np.ndarray:
    """Total motion in the bottom-left-origin frame get_world_positions works in."""
    return np.array([(_PANEL_HEIGHT - path[-1][0]) - (_PANEL_HEIGHT - path[0][0]),
                     path[-1][1] - path[0][1]], dtype=np.float64)


def _drag(space: Space, view_type: ViewType, angle: float, scalar: float,
          rederive: bool = True) -> np.ndarray:
    harness = _Harness(_controller(angle, scalar), space, view_type)
    for point in _PATH:
        harness.motion(point, rederive=rederive)
    return np.asarray(harness._transform_controller.TransformModel.target_offset,
                      dtype=np.float64)


_CONFIGS = ((0.0, 1.0), (0.3, 1.0), (0.0, 1.4))


class TestTheDragTracksOneToOne(unittest.TestCase):
    """The accumulated offset equals the total screen motion."""

    def test_the_source_panel_tracks_one_to_one(self) -> None:
        expected = _screen_delta(_PATH)
        for angle, scalar in _CONFIGS:
            with self.subTest(angle=angle, scalar=scalar):
                offset = _drag(Space.Source, ViewType.Source, angle, scalar)
                np.testing.assert_allclose(expected, offset, atol=1e-6)

    def test_the_composite_panel_tracks_one_to_one(self) -> None:
        expected = _screen_delta(_PATH)
        for angle, scalar in _CONFIGS:
            with self.subTest(angle=angle, scalar=scalar):
                offset = _drag(Space.Source, ViewType.Composite, angle, scalar)
                np.testing.assert_allclose(expected, offset, atol=1e-6)

    def test_rotation_and_scale_do_not_skew_the_drag(self) -> None:
        """The drag quantity is camera-derived, so it must not pick up R or s."""
        baseline = _drag(Space.Source, ViewType.Source, 0.0, 1.0)
        for angle, scalar in ((0.5, 1.0), (0.0, 2.0), (0.5, 2.0)):
            with self.subTest(angle=angle, scalar=scalar):
                np.testing.assert_allclose(
                    baseline, _drag(Space.Source, ViewType.Source, angle, scalar), atol=1e-6)


class TestTheOriginMustBeRederived(unittest.TestCase):
    """Why the second get_world_positions call cannot be removed."""

    def test_the_standalone_origin_is_transform_independent(self) -> None:
        """On the standalone panels re-deriving is provably a no-op."""
        for space, view in ((Space.Source, ViewType.Source),
                            (Space.Target, ViewType.Target)):
            for angle, scalar in _CONFIGS:
                with self.subTest(space=space.name, angle=angle, scalar=scalar):
                    harness = _Harness(_controller(angle, scalar), space, view)
                    before = harness._world_point_for_translate(
                        harness.get_world_positions((400.0, 600.0)))
                    harness._transform_controller.Translate(
                        np.array([37.0, -19.0]), space=space)
                    after = harness._world_point_for_translate(
                        harness.get_world_positions((400.0, 600.0)))
                    np.testing.assert_allclose(before, after, atol=1e-6)

    def test_the_composite_origin_moves_with_the_transform(self) -> None:
        """On composite the same screen point maps elsewhere once the layer moves."""
        offset = np.array([37.0, -19.0])
        harness = _Harness(_controller(), Space.Source, ViewType.Composite)
        before = harness._world_point_for_translate(
            harness.get_world_positions((400.0, 600.0)))
        harness._transform_controller.Translate(offset, space=Space.Source)
        after = harness._world_point_for_translate(
            harness.get_world_positions((400.0, 600.0)))
        self.assertFalse(np.allclose(before, after))
        np.testing.assert_allclose(np.abs(offset), np.abs(after - before), atol=1e-6)

    def test_reusing_the_stale_origin_overshoots_on_composite(self) -> None:
        """Guards the removal this test file exists to prevent."""
        expected = _screen_delta(_PATH)
        stale = _drag(Space.Source, ViewType.Composite, 0.0, 1.0, rederive=False)
        self.assertFalse(np.allclose(expected, stale),
                         'dropping the re-derivation must visibly break composite drag')
        self.assertGreater(np.max(np.abs(stale)), np.max(np.abs(expected)),
                           'the stale origin double-counts, so the layer overshoots')

    def test_reusing_the_stale_origin_is_harmless_on_the_source_panel(self) -> None:
        """Which is why this looks like dead code until composite is considered."""
        np.testing.assert_allclose(
            _drag(Space.Source, ViewType.Source, 0.0, 1.0, rederive=True),
            _drag(Space.Source, ViewType.Source, 0.0, 1.0, rederive=False), atol=1e-6)


if __name__ == '__main__':
    unittest.main()
