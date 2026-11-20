"""A STOS panel keeps one active command, so one drag pans the camera once.

James (2026-11-19): in Source and Target, right-drag panned at twice the cursor speed. A command that
finished queued its "activate the next command" callback; when the transform model was replaced before that
callback ran, the panel activated a new default command at once, and the late callback then activated a
second one. The second chained onto the first's mouse handler, so both handled each move.
"""
from __future__ import annotations

import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from PyQt6.QtCore import QCoreApplication, QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication, QWidget

import pyre
from pyre.commands.uicommandbase import UICommandBase
from pyre.interfaces import ControlPointAction
from pyre.state.managers.command_queue import CommandQueue
from pyre.ui.widgets.imagetransformviewpanel import ImageTransformViewPanel


class _CountingCommand(UICommandBase):
    """Stands in for DefaultTransformCommand: binds mouse events and counts moves."""
    moves: int

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent=parent)
        self.moves = 0

    def subscribe_to_parent(self) -> None:
        self._bind_mouse_events()

    def unsubscribe_to_parent(self) -> None:
        self._unbind_mouse_events()

    def on_mouse_motion(self, event: QMouseEvent) -> None:
        self.moves += 1

    def can_execute(self) -> bool:
        return True

    def on_key_down(self, event) -> None:
        pass

    def on_key_up(self, event) -> None:
        pass

    def on_mouse_press(self, event) -> None:
        pass

    def on_mouse_release(self, event) -> None:
        pass

    def on_mouse_scroll(self, event) -> None:
        pass


def _panel(widget: QWidget, created: list[_CountingCommand]) -> SimpleNamespace:
    """The attributes activate_command and _on_transform_model_changed use."""
    def factory(**_kwargs) -> _CountingCommand:
        command = _CountingCommand(widget)
        created.append(command)
        return command

    panel = SimpleNamespace(
        _command=None,
        _command_queue=CommandQueue(),
        _glpanel=widget,
        _transform_type_to_command_action_map={'rigid': {ControlPointAction.NONE: factory}},
        transform_controller=SimpleNamespace(type='rigid'),
        camera=None, space=None, _selected_points=None, view_type=None,
        _image_transform_view=None, _transform_controller_view=None,
        _update_fixed_layer_hint=lambda: None, mark_image_layer_dirty=lambda: None,
    )
    panel.activate_command = lambda previous_command=None: ImageTransformViewPanel.activate_command(
        panel, previous_command)
    return panel


class TestPanelCommandActivation(unittest.TestCase):
    app: QApplication

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def test_a_model_change_before_the_completion_callback_leaves_one_command_handling_moves(self) -> None:
        widget = QWidget()
        created: list[_CountingCommand] = []
        panel = _panel(widget, created)
        panel.activate_command()
        first = created[0]

        first.cancel()  # completion callback is queued with QTimer.singleShot(0)
        model = MagicMock(type='rigid')
        ImageTransformViewPanel._on_transform_model_changed(panel, MagicMock(), model, model)
        QCoreApplication.processEvents()  # the late callback runs now

        point = QPointF(5, 5)
        widget.mouseMoveEvent(QMouseEvent(QMouseEvent.Type.MouseMove, point, widget.mapToGlobal(point),
                                          Qt.MouseButton.NoButton, Qt.MouseButton.RightButton,
                                          Qt.KeyboardModifier.NoModifier))

        active = [c for c in created if c.status == pyre.CommandStatus.Active]
        self.assertEqual(len(active), 1)
        self.assertIs(panel._command, active[0])
        self.assertEqual([c.moves for c in created], [0] * (len(created) - 1) + [1])


if __name__ == '__main__':
    unittest.main()
