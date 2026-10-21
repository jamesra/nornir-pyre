"""Hover-and-Space must register only the hovered point, not every earlier press's point.

Regression for the selection snowball: ``RegisterControlPointCommand`` added the
hovered point to the shared selection, and the controller re-selects queued
points once the queue goes idle, so press N re-registered all N earlier points.
"""

from __future__ import annotations

import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import numpy as np
from nornir_imageregistration.alignment_record import AlignmentRecord
from nornir_imageregistration.transforms.meshwithrbffallback import MeshWithRBFFallback
from PyQt6.QtCore import Qt

from pyre.commands.stos.actionmaphelpers import resolve_space_register_action
from pyre.commands.stos.registercontrolpointcommand import RegisterControlPointCommand
from pyre.controllers.transformcontroller import TransformController
from pyre.interfaces.action import ControlPointAction
from pyre.observable import ObservableSet
from pyre.selection_event_data import (
    InputEvent,
    InputModifiers,
    InputSource,
    SelectionEventData,
)
from pyre.settings.app import AppSettings


def _grid_mesh() -> MeshWithRBFFallback:
    """A 4x4 identity mesh with 50 px spacing."""
    points = np.array(
        [[i * 50.0, j * 50.0, i * 50.0, j * 50.0] for i in range(4) for j in range(4)],
        dtype=np.float64)
    return MeshWithRBFFallback(points)


def _space_event(selection: ObservableSet[int]) -> SelectionEventData:
    """A plain Space key press with the current shared selection."""
    return SelectionEventData(
        camera=MagicMock(scale=1.0),
        source=InputSource.Keyboard,
        input=InputEvent.Press,
        modifiers=InputModifiers.NoModifiers,
        position=np.zeros(2, dtype=float),
        keycode=Qt.Key.Key_Space,
        existing_selections=selection,
    )


class TestSpaceRegisterSnowball(unittest.TestCase):
    """Each hover-and-Space press aligns only what the user asked for."""

    selection: ObservableSet[int]
    controller: TransformController
    aligned: list[tuple[float, float]]

    def setUp(self) -> None:
        self.selection = ObservableSet(initial_set=None)
        self.controller = TransformController(_grid_mesh(), selected_points=self.selection)
        self.controller._point_in_view_fn = lambda _index: True
        self.aligned = []

    def _align(self, **kwargs: object) -> AlignmentRecord:
        target = np.asarray(kwargs["target_controlpoint"], dtype=np.float64)
        self.aligned.append((float(target[0]), float(target[1])))
        return AlignmentRecord(peak=(0.0, 0.0), weight=0.0, angle=0.0)  # weight 0: no move

    @contextmanager
    def _synchronous_registration(self) -> Iterator[None]:
        """Run alignments inline with a fake aligner and no shared-memory images."""
        controller = self.controller
        original_enqueue = controller.enqueue_point_registrations

        def enqueue_with_fake_aligner(indices, **kwargs):
            kwargs["align_fn"] = self._align
            return original_enqueue(indices, **kwargs)

        with patch("pyre.controllers.transformcontroller.QApplication") as qapp, \
                patch("pyre.commands.stos.registercontrolpointcommand.contrasted_permutation_helper",
                      return_value=None), \
                patch.object(controller, "enqueue_point_registrations",
                             side_effect=enqueue_with_fake_aligner):
            qapp.instance.return_value = None
            yield

    def _press_space(self, hovered: set[int]) -> int:
        """Resolve Space like the default command, run the command, return points aligned."""
        result = resolve_space_register_action(_space_event(self.selection), hovered)
        assert result is not None
        self.assertEqual(result.action, ControlPointAction.REGISTER)
        command = RegisterControlPointCommand(
            selected_points=self.selection,
            command_points=set(result.point_indicies or ()),
            source_image="source",
            target_image="target",
            transform_controller=self.controller,
            config=MagicMock(),
            settings=AppSettings(),
        )
        command._image_manager = {"source": None, "target": None}  # type: ignore[assignment]
        before = len(self.aligned)
        command.activate()
        return len(self.aligned) - before

    def test_hover_presses_align_one_point_each(self) -> None:
        with self._synchronous_registration():
            counts = [self._press_space({hovered}) for hovered in (5, 6, 9, 10, 1)]
        self.assertEqual(counts, [1, 1, 1, 1, 1])
        self.assertEqual(set(self.selection), set(),
                         "a hovered point must not be left selected after it registers")

    def test_selection_registers_whole_set_and_is_restored(self) -> None:
        self.selection.update({2, 7, 11})
        with self._synchronous_registration():
            count = self._press_space(set())
        self.assertEqual(count, 3)
        self.assertEqual(set(self.selection), {2, 7, 11})

    def test_selection_plus_hover_registers_both_but_restores_only_selection(self) -> None:
        self.selection.update({2, 7})
        with self._synchronous_registration():
            first = self._press_space({12})
            second = self._press_space({13})
        self.assertEqual(first, 3)
        # The user's selection is still selected, so it registers again; the
        # previously hovered point 12 does not.
        self.assertEqual(second, 3)
        self.assertEqual(set(self.selection), {2, 7})


if __name__ == "__main__":
    unittest.main()
