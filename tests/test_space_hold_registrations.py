"""A held Space registers each control point once per hold.

Holding Space sends key auto-repeat presses (about 30 per second). Each repeat
queued the hovered point again as soon as its previous alignment finished, so a
held Space re-registered the same point several times a second, nudging it
0.3-1 px every time and redrawing the composite continuously. During one hold a
point now registers on the first press that reaches it; sweeping onto new points
still registers them, and a new physical press starts a new hold.
"""

from __future__ import annotations

import unittest
from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import numpy as np
from nornir_imageregistration.alignment_record import AlignmentRecord
from nornir_imageregistration.transforms.meshwithrbffallback import MeshWithRBFFallback
from pyre.commands.stos.registercontrolpointcommand import RegisterControlPointCommand
from pyre.controllers.control_point_registration_queue import SpaceHoldRegistrations
from pyre.controllers.transformcontroller import TransformController
from pyre.observable import ObservableSet
from pyre.settings.app import AppSettings


def _grid_mesh() -> MeshWithRBFFallback:
    """A 4x4 identity mesh with 50 px spacing."""
    points = np.array(
        [[i * 50.0, j * 50.0, i * 50.0, j * 50.0] for i in range(4) for j in range(4)],
        dtype=np.float64)
    return MeshWithRBFFallback(points)


class TestSpaceHoldRegistrations(unittest.TestCase):
    """The tracker itself."""

    def test_no_hold_passes_everything(self) -> None:
        hold = SpaceHoldRegistrations()
        self.assertEqual(hold.claim([1, 2]), {1, 2})
        self.assertEqual(hold.claim([1, 2]), {1, 2})

    def test_hold_claims_each_id_once_until_a_new_hold(self) -> None:
        hold = SpaceHoldRegistrations()
        hold.begin()
        self.assertEqual(hold.claim([1, 2]), {1, 2})
        self.assertEqual(hold.claim([1, 2, 3]), {3})
        self.assertEqual(hold.claim([3]), set())
        hold.begin()
        self.assertEqual(hold.claim([1]), {1})
        hold.end()
        self.assertFalse(hold.active)
        self.assertEqual(hold.claim([1]), {1})


class TestHeldSpaceRegistersOncePerPoint(unittest.TestCase):
    """Auto-repeat presses through the real command and controller."""

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
        """Run alignments inline, so each finishes before the next repeat arrives."""
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

    def _press(self, hovered: set[int], *, register_all: bool = False) -> int:
        """Run one Space press (physical or repeat) and return the points aligned."""
        command = RegisterControlPointCommand(
            selected_points=self.selection,
            command_points=hovered,
            source_image="source",
            target_image="target",
            register_all=register_all,
            transform_controller=self.controller,
            config=MagicMock(),
            settings=AppSettings(),
        )
        command._image_manager = {"source": None, "target": None}  # type: ignore[assignment]
        before = len(self.aligned)
        command.activate()
        return len(self.aligned) - before

    def test_repeats_over_one_point_register_it_once(self) -> None:
        hold = self.controller.space_hold
        with self._synchronous_registration():
            hold.begin()
            counts = [self._press({5}) for _ in range(10)]
            hold.end()
        self.assertEqual(counts, [1] + [0] * 9)

    def test_sweeping_onto_new_points_registers_each_once(self) -> None:
        hold = self.controller.space_hold
        with self._synchronous_registration():
            hold.begin()
            counts = [self._press({hovered}) for hovered in (5, 5, 6, 6, 5, 9)]
            hold.end()
        self.assertEqual(counts, [1, 0, 1, 0, 0, 1])

    def test_selection_registers_once_and_new_hold_registers_again(self) -> None:
        self.selection.update({2, 7})
        hold = self.controller.space_hold
        with self._synchronous_registration():
            hold.begin()
            first = self._press(set())
            repeat = self._press(set())
            hold.begin()  # release and press again
            again = self._press(set())
            hold.end()
        self.assertEqual((first, repeat, again), (2, 0, 2))

    def test_shift_space_registers_all_once_per_hold(self) -> None:
        hold = self.controller.space_hold
        n_points = self.controller.NumPoints
        with self._synchronous_registration():
            hold.begin()
            first = self._press(set(), register_all=True)
            repeat = self._press(set(), register_all=True)
            hold.end()
        self.assertEqual((first, repeat), (n_points, 0))

    def test_without_a_hold_every_press_registers(self) -> None:
        with self._synchronous_registration():
            counts = [self._press({5}) for _ in range(3)]
        self.assertEqual(counts, [1, 1, 1])


if __name__ == "__main__":
    unittest.main()
