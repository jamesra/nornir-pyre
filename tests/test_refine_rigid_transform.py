"""Tests for rigid refine helpers, action maps, and pivot preservation."""

from __future__ import annotations

import math
import unittest
from unittest.mock import MagicMock, patch

import numpy as np
from PyQt6.QtCore import Qt

import nornir_imageregistration
from nornir_imageregistration.settings import SliceToSliceMethod, StosBruteSettings
from nornir_imageregistration.transforms import CenteredSimilarity2DTransform

from pyre.common import (
    REFINE_ANGLE_HALF_WIDTH_DEG,
    REFINE_ANGLE_STEP_DEG,
    RefineRigidTransformLocal,
    _preserve_rigid_refine_attributes,
    build_refine_angle_grid_deg,
)
from pyre.commands.stos.actionmaphelpers import resolve_space_register_action
from pyre.commands.stos.rigidtransformactionmap import RigidTransformActionMap
from pyre.interfaces.action import ControlPointAction
from pyre.selection_event_data import InputEvent, InputModifiers, InputSource, SelectionEventData
from pyre.settings import AppSettings


class _MinimalImageManager(dict):
    """Minimal mapping used in place of Pyre's ImageManager."""

    def __contains__(self, key: object) -> bool:
        return super().__contains__(str(key))

    def __getitem__(self, key: object):
        return super().__getitem__(str(key))


def _keyboard_space_event(*, shift: bool = False) -> SelectionEventData:
    modifiers = InputModifiers.ShiftKey if shift else InputModifiers(0)
    return SelectionEventData(
        camera=MagicMock(),
        source=InputSource.Keyboard,
        input=InputEvent.Press,
        modifiers=modifiers,
        position=np.array([0.0, 0.0], dtype=float),
        keycode=Qt.Key.Key_Space,
    )


class TestBuildRefineAngleGrid(unittest.TestCase):
    """Absolute angle grids for local rigid refine."""

    def test_centered_grid_has_expected_count_and_spacing(self) -> None:
        grid = build_refine_angle_grid_deg(12.0)
        self.assertEqual(len(grid), 16)
        self.assertAlmostEqual(float(grid[0]), 4.5)
        self.assertAlmostEqual(float(grid[-1]), 19.5)
        self.assertTrue(np.allclose(np.diff(grid), REFINE_ANGLE_STEP_DEG))

    def test_grid_near_180_is_absolute_not_wrapped(self) -> None:
        grid = build_refine_angle_grid_deg(178.0)
        self.assertAlmostEqual(float(grid[0]), 170.5)
        self.assertAlmostEqual(float(grid[-1]), 185.5)
        self.assertAlmostEqual(REFINE_ANGLE_HALF_WIDTH_DEG, 7.5)


class TestPreserveRigidRefineAttributes(unittest.TestCase):
    """Attribute preservation after brute registration."""

    def test_keeps_brute_angle_and_scalar(self) -> None:
        current = CenteredSimilarity2DTransform(
            target_offset=(1.0, 2.0),
            source_rotation_center=(10.0, 20.0),
            angle=math.radians(5.0),
            scalar=1.07,
        )
        result = CenteredSimilarity2DTransform(
            target_offset=(3.0, 4.0),
            source_rotation_center=(30.0, 40.0),
            angle=math.radians(6.0),
            scalar=0.95,
        )
        preserved = _preserve_rigid_refine_attributes(result, current)
        self.assertIsInstance(preserved, CenteredSimilarity2DTransform)
        self.assertAlmostEqual(preserved.scalar, 0.95)
        self.assertAlmostEqual(float(preserved.angle), math.radians(6.0))

    def test_pivot_swap_keeps_the_brute_mapping(self) -> None:
        """Adopting the user's pivot must not move the registered result."""
        current = CenteredSimilarity2DTransform(
            target_offset=(1.0, 2.0),
            source_rotation_center=(120.0, 150.0),
            angle=math.radians(5.0),
            scalar=1.0,
        )
        result = CenteredSimilarity2DTransform(
            target_offset=(-30.0, 25.0),
            source_rotation_center=(2092.0, 2150.0),
            angle=math.radians(8.4),
            scalar=1.02,
        )
        probe = np.array([[100.0, 100.0], [2092.0, 2150.0], [4000.0, 300.0]])
        expected = np.asarray(result.Transform(probe), dtype=float)

        preserved = _preserve_rigid_refine_attributes(result, current)

        np.testing.assert_allclose(
            np.asarray(preserved.source_space_center_of_rotation, dtype=float), [120.0, 150.0])
        np.testing.assert_allclose(np.asarray(preserved.Transform(probe), dtype=float), expected, atol=0.05)


class TestRefineRigidTransformLocal(unittest.TestCase):
    """Bridge passes BruteForce settings seeded from the current transform."""

    def setUp(self) -> None:
        self._image_manager = _MinimalImageManager()
        self._image_manager["Source"] = MagicMock(shape=(64, 64))
        self._image_manager["Target"] = MagicMock(shape=(64, 64))
        self._app_settings = MagicMock()
        self._app_settings.stos.stos_filename = None
        self._app_settings.stos.source_image = None
        self._app_settings.stos.target_image = None
        self._app_settings.stos.brute_registration = StosBruteSettings(
            method=SliceToSliceMethod.LogPolar,
            try_flipped=True,
        )
        self._current = CenteredSimilarity2DTransform(
            target_offset=(1.0, 2.0),
            source_rotation_center=(32.0, 32.0),
            angle=math.radians(12.0),
            scalar=1.05,
        )

    @patch("pyre.common.stos.SliceToSliceRigidRegistrationWithPreprocessedImages")
    @patch("pyre.common.resolve_source_and_target_image_data")
    def test_current_angle_only_searches_scale_at_1024(
            self,
            mock_resolve: MagicMock,
            mock_register: MagicMock,
    ) -> None:
        mock_resolve.return_value = (
            self._image_manager["Source"],
            self._image_manager["Target"],
        )
        align_record = MagicMock()
        align_record.ToImageTransform.return_value = CenteredSimilarity2DTransform(
            target_offset=(5.0, 6.0),
            source_rotation_center=(32.0, 32.0),
            angle=math.radians(12.0),
            scalar=0.9,
        )
        mock_register.return_value = align_record
        self._app_settings.stos.brute_registration.search_scale = False

        result = RefineRigidTransformLocal(
            current_transform=self._current,
            search_angle=False,
            source_image_key="Source",
            target_image_key="Target",
            image_manager=self._image_manager,
            app_settings=self._app_settings,
        )

        settings = mock_register.call_args.kwargs["settings"]
        self.assertEqual(settings.method, SliceToSliceMethod.BruteForce)
        self.assertFalse(settings.try_flipped)
        self.assertTrue(settings.search_scale)
        self.assertEqual(settings.larget_dimension, 1024)
        self.assertAlmostEqual(settings.initial_scale_hint, 1.05)
        self.assertEqual(len(list(settings.angles)), 1)
        self.assertAlmostEqual(float(next(iter(settings.angles))), 12.0)
        assert result is not None
        self.assertIsInstance(result, CenteredSimilarity2DTransform)
        self.assertAlmostEqual(result.scalar, 0.9)

    @patch("pyre.common.stos.SliceToSliceRigidRegistrationWithPreprocessedImages")
    @patch("pyre.common.resolve_source_and_target_image_data")
    def test_angle_search_covers_plus_minus_7_5_degrees(
            self,
            mock_resolve: MagicMock,
            mock_register: MagicMock,
    ) -> None:
        mock_resolve.return_value = (
            self._image_manager["Source"],
            self._image_manager["Target"],
        )
        align_record = MagicMock()
        align_record.ToImageTransform.return_value = CenteredSimilarity2DTransform(
            target_offset=(5.0, 6.0),
            source_rotation_center=(32.0, 32.0),
            angle=math.radians(13.0),
            scalar=0.92,
        )
        mock_register.return_value = align_record

        result = RefineRigidTransformLocal(
            current_transform=self._current,
            search_angle=True,
            source_image_key="Source",
            target_image_key="Target",
            image_manager=self._image_manager,
            app_settings=self._app_settings,
        )

        settings = mock_register.call_args.kwargs["settings"]
        self.assertTrue(settings.search_scale)
        self.assertAlmostEqual(settings.initial_scale_hint, 1.05)
        self.assertEqual(len(list(settings.angles)), 16)
        self.assertAlmostEqual(float(list(settings.angles)[0]), 4.5)
        self.assertAlmostEqual(float(list(settings.angles)[-1]), 19.5)
        assert result is not None
        self.assertIsInstance(result, CenteredSimilarity2DTransform)
        self.assertAlmostEqual(result.scalar, 0.92)

    def test_non_rigid_raises(self) -> None:
        mesh = MagicMock()
        with self.assertRaises(TypeError):
            RefineRigidTransformLocal(
                current_transform=mesh,  # type: ignore[arg-type]
                image_manager=self._image_manager,
                app_settings=self._app_settings,
            )


class TestRigidRefineActionMaps(unittest.TestCase):
    """Space routing differs for rigid vs control-point transforms."""

    def test_rigid_space_maps_to_refine_actions(self) -> None:
        action_map = RigidTransformActionMap(config=AppSettings())
        space = action_map.get_action(_keyboard_space_event(shift=False))
        shift_space = action_map.get_action(_keyboard_space_event(shift=True))
        self.assertEqual(space.action, ControlPointAction.REFINE_RIGID)
        self.assertEqual(shift_space.action, ControlPointAction.REFINE_RIGID_ANGLE_SEARCH)

    def test_helper_still_maps_space_to_register_for_mesh_grid(self) -> None:
        space = resolve_space_register_action(_keyboard_space_event(shift=False), set())
        shift_space = resolve_space_register_action(_keyboard_space_event(shift=True), set())
        assert space is not None
        assert shift_space is not None
        self.assertEqual(space.action, ControlPointAction.REGISTER)
        self.assertEqual(shift_space.action, ControlPointAction.REGISTER_ALL)

    def test_space_register_unions_selection_and_hover(self) -> None:
        event = _keyboard_space_event(shift=False)
        event.existing_selections = {2, 5}  # type: ignore[assignment]
        result = resolve_space_register_action(event, {7})
        assert result is not None
        self.assertEqual(result.action, ControlPointAction.REGISTER)
        self.assertEqual(result.point_indicies, {2, 5, 7})


if __name__ == "__main__":
    unittest.main()
