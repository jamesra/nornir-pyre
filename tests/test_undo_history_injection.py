"""Spacebar and grid-relax undo reach the real Ctrl+Z history through dependency injection.

2026-11-19: Ctrl+Z after Space did not undo the move. The undo was saved through an ``@inject``
closure defined inside the method; dependency_injector only injects functions that exist when the
package is wired, so the closure got the ``Provide`` marker, the save raised, and the error was
logged at debug level. These tests wire the history the way the launcher does.
"""

from __future__ import annotations

import sys
import unittest

import numpy as np
import pyre.commands.transform_undo
import pyre.controllers.masked_grid_relax
import pyre.space
from dependency_injector import providers
from nornir_imageregistration.transforms.meshwithrbffallback import MeshWithRBFFallback
from pyre.container import IContainer
from pyre.controllers.transformcontroller import TransformController
from pyre.observable import ObservableSet
from pyre.settings.app import AppSettings
from pyre.state.managers.command_history import CommandHistory


class TestUndoHistoryInjection(unittest.TestCase):

    def setUp(self) -> None:
        self.history = CommandHistory()
        self.settings = AppSettings()
        self.settings.stos.grid_refine.masked_relax_min_unmasked = 0.4
        IContainer.history_manager.override(providers.Singleton(lambda: self.history))
        IContainer.settings.override(providers.Singleton(lambda: self.settings))
        self.addCleanup(IContainer.history_manager.reset_override)
        self.addCleanup(IContainer.settings.reset_override)
        container = IContainer()
        container.wire(modules=[sys.modules['pyre.commands.transform_undo'],
                                sys.modules['pyre.controllers.masked_grid_relax']])
        self.addCleanup(container.unwire)

    def test_a_spacebar_batch_can_be_undone(self) -> None:
        points = np.array([[float(i * 10), float(i * 20), float(i * 100), float(i * 200)] for i in range(4)])
        controller = TransformController(MeshWithRBFFallback(points), selected_points=ObservableSet(initial_set=None))
        before = controller.copy_points()
        controller._registration_batch_undo_points = before.copy()
        controller._registration_batch_had_apply = True
        controller.MovePoint(1, 5.0, 3.0, space=pyre.space.Space.Target)
        self.assertFalse(np.allclose(controller.copy_points(), before))

        controller._commit_registration_batch_undo()
        self.assertEqual(1, self.history.HistoryDepth)
        self.history.Undo()
        np.testing.assert_allclose(controller.copy_points(), before)

    def test_the_min_unmasked_setting_is_read(self) -> None:
        self.assertEqual(0.4, pyre.controllers.masked_grid_relax.resolve_min_unmasked())


if __name__ == '__main__':
    unittest.main()
