"""Tests for control-point hit testing during drag and zoom."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import numpy as np

from pyre.commands.stos.actionmaphelpers import (
    drag_translate_interactions,
    find_control_point_interactions,
)
from pyre.selection_event_data import InputEvent, SelectionEventData
from pyre.viewmodels.controlpointmap import ControlPointMap
from pyre.controllers.transformcontroller import TransformController
from pyre.space import Space
from nornir_imageregistration.transforms.meshwithrbffallback import MeshWithRBFFallback


def _mesh() -> MeshWithRBFFallback:
    points = np.array([
        [10.0, 20.0, 100.0, 200.0],
        [30.0, 40.0, 300.0, 400.0],
        [50.0, 60.0, 500.0, 600.0],
        [70.0, 80.0, 700.0, 800.0],
    ], dtype=np.float32)
    return MeshWithRBFFallback(points)


class TestControlPointPick(unittest.TestCase):
  """Nearest-point pick and drag selection retention."""

  def test_find_nearest_within_returns_single_point(self) -> None:
      cmap = ControlPointMap(TransformController(_mesh()), Space.Source)
      hits = cmap.find_nearest_within(np.array([100.5, 200.5]), 5.0)
      self.assertEqual(hits, {0})

  def test_pick_radius_matches_glyph_half_extent(self) -> None:
      cmap = ControlPointMap(TransformController(_mesh()), Space.Source)
      inside = np.array([100.0, 204.0])
      outside = np.array([100.0, 206.0])
      self.assertEqual(find_control_point_interactions(cmap, inside, 10.0, 1.0), {0})
      self.assertEqual(find_control_point_interactions(cmap, outside, 10.0, 1.0), set())

  def test_find_nearest_within_rejects_non_finite_query(self) -> None:
      cmap = ControlPointMap(TransformController(_mesh()), Space.Source)
      self.assertEqual(cmap.find_nearest_within(np.array([np.nan, 0.0]), 5.0), set())
      self.assertEqual(cmap.find_nearest_within(np.array([np.inf, 1.0]), 5.0), set())

  def test_target_map_rebuilds_after_inplace_target_point_move(self) -> None:
      """In-place TargetPoints edits must refresh Target-view hit testing."""
      controller = TransformController(_mesh())
      cmap = ControlPointMap(controller, Space.Target)
      original = np.array(controller.TargetPoints[0], copy=True)
      self.assertEqual(cmap.find_nearest_within(original, 1.0), {0})
      controller.MovePoint(0, ImageDX=50.0, ImageDY=40.0, space=Space.Target)
      self.assertEqual(cmap.find_nearest_within(original, 1.0), set())
      moved = np.array(controller.TargetPoints[0], copy=True)
      self.assertEqual(cmap.find_nearest_within(moved, 1.0), {0})

  def test_interactive_drag_skips_kdtree_and_picks_live_points(self) -> None:
      """Mouse-move during CP drag must not rebuild the KD-tree; pick uses live points."""
      controller = TransformController(_mesh())
      cmap = ControlPointMap(controller, Space.Target)
      original = np.array(controller.TargetPoints[0], copy=True)
      controller.begin_interactive_edit(Space.Target)
      try:
          with patch("pyre.viewmodels.controlpointmap.scipy.spatial.KDTree") as mock_tree:
              controller.MovePoint(0, ImageDX=50.0, ImageDY=40.0, space=Space.Target)
              mock_tree.assert_not_called()
          moved = np.array(controller.TargetPoints[0], copy=True)
          self.assertTrue(cmap._kdtree_stale)
          self.assertEqual(cmap.find_nearest_within(original, 1.0), set())
          self.assertEqual(cmap.find_nearest_within(moved, 1.0), {0})
          self.assertEqual(cmap.find_in_rect(moved - 1.0, moved + 1.0), {0})
      finally:
          if controller.interactive_edit_in_progress:
              controller.end_interactive_edit()

  def test_kdtree_rebuilds_on_pick_after_interactive_drag(self) -> None:
      """After mouse-up, the next pick rebuilds the tree without waiting for remesh/RBF."""
      controller = TransformController(_mesh())
      cmap = ControlPointMap(controller, Space.Target)
      original = np.array(controller.TargetPoints[0], copy=True)
      controller.begin_interactive_edit(Space.Target)
      try:
          controller.MovePoint(0, ImageDX=50.0, ImageDY=40.0, space=Space.Target)
          self.assertTrue(cmap._kdtree_stale)
      finally:
          if controller.interactive_edit_in_progress:
              controller.end_interactive_edit()
      self.assertTrue(cmap._kdtree_stale)
      moved = np.array(controller.TargetPoints[0], copy=True)
      self.assertEqual(cmap.find_nearest_within(moved, 1.0), {0})
      self.assertFalse(cmap._kdtree_stale)
      self.assertEqual(cmap.find_nearest_within(original, 1.0), set())

  def test_drag_on_empty_space_does_not_reuse_selection(self) -> None:
      event = SelectionEventData(
          camera=None,  # type: ignore[arg-type]
          source=None,  # type: ignore[arg-type]
          input=InputEvent.Drag,
          modifiers=0,
          position=np.array([0.0, 0.0]),
          existing_selections={2, 5},
      )
      self.assertEqual(drag_translate_interactions(event, set()), set())


if __name__ == "__main__":
    unittest.main()
