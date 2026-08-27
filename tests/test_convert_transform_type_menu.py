"""Tests for Convert Transform Type menu checkmarks."""

from __future__ import annotations

import sys
import unittest

from PyQt6.QtGui import QAction, QActionGroup
from PyQt6.QtWidgets import QApplication, QWidget
from nornir_imageregistration.transforms import TransformType

from pyre.ui.windows.stoswindow import (
    convert_transform_type_actions,
    sync_convert_transform_type_menu,
)


class _ConvertTypeMenuHost:
    _action_convert_rigid: QAction
    _action_convert_grid: QAction
    _action_convert_mesh: QAction
    _action_convert_rbf: QAction

    def __init__(self, parent: QWidget) -> None:
        self._action_convert_rigid = QAction("&Rigid", parent)
        self._action_convert_grid = QAction("&Grid", parent)
        self._action_convert_mesh = QAction("&Mesh", parent)
        self._action_convert_rbf = QAction("&RBF", parent)
        group = QActionGroup(parent)
        group.setExclusive(True)
        for action in convert_transform_type_actions(self).values():
            action.setCheckable(True)
            group.addAction(action)


class TestConvertTransformTypeMenuCheck(unittest.TestCase):
    """The current transform type is the checked Convert Transform Type item."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication(sys.argv)

    def test_menu_covers_every_transform_type(self) -> None:
        parent = QWidget()
        try:
            mapped = convert_transform_type_actions(_ConvertTypeMenuHost(parent))
            self.assertEqual(set(mapped.keys()), set(TransformType))
        finally:
            parent.deleteLater()

    def test_checks_only_the_current_transform_type(self) -> None:
        parent = QWidget()
        try:
            host = _ConvertTypeMenuHost(parent)
            for current in TransformType:
                sync_convert_transform_type_menu(host, current)
                for transform_type, action in convert_transform_type_actions(host).items():
                    self.assertEqual(
                        action.isChecked(),
                        transform_type == current,
                        f"{current.value}: {transform_type.value} checked={action.isChecked()}",
                    )
        finally:
            parent.deleteLater()


if __name__ == "__main__":
    unittest.main()
