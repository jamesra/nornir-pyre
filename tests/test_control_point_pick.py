"""Tests for control-point hit testing during drag and zoom."""

from __future__ import annotations

import unittest

import numpy as np

from pyre.commands.stos.actionmaphelpers import drag_translate_interactions
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
      hits = cmap.find_nearest_within(np.array([10.5, 20.5]), 5.0)
      self.assertEqual(hits, {0})

  def test_drag_translate_uses_existing_selection(self) -> None:
      event = SelectionEventData(
          camera=None,  # type: ignore[arg-type]
          source=None,  # type: ignore[arg-type]
          input=InputEvent.Drag,
          modifiers=0,
          position=np.array([0.0, 0.0]),
          existing_selections={2, 5},
      )
      self.assertEqual(drag_translate_interactions(event, set()), {2, 5})


if __name__ == "__main__":
    unittest.main()
