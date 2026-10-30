"""Tests for grid transform type conversion settings dialog."""

from __future__ import annotations

import sys
import unittest
from unittest.mock import patch

from PyQt6.QtWidgets import QApplication, QDialog

from pyre.ui.windows.grid_transform_settings_dialog import (
    GridTransformSettingsDialog,
    GridTransformSettingsResult,
)


class TestGridTransformSettingsDialog(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication(sys.argv)

    def test_default_grid_dimensions_are_eight_by_eight(self) -> None:
        dlg = GridTransformSettingsDialog()
        self.assertEqual(8, dlg.rows)
        self.assertEqual(8, dlg.columns)
        self.assertEqual((8, 8), dlg.grid_dims)

    def test_get_settings_returns_none_when_cancelled(self) -> None:
        with patch.object(GridTransformSettingsDialog, "exec", return_value=QDialog.DialogCode.Rejected):
            self.assertIsNone(GridTransformSettingsDialog.GetGridTransformSettings())

    def test_get_settings_returns_dimensions_when_accepted(self) -> None:
        real_init = GridTransformSettingsDialog.__init__

        def init_with_custom_dims(self, parent=None, **kwargs):
            real_init(self, parent, **kwargs)
            self.height_ctrl.setValue(10)
            self.width_ctrl.setValue(12)

        with patch.object(GridTransformSettingsDialog, "__init__", init_with_custom_dims):
            with patch.object(GridTransformSettingsDialog, "exec", return_value=QDialog.DialogCode.Accepted):
                result = GridTransformSettingsDialog.GetGridTransformSettings()

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual((10, 12), result.grid_dims)

    def test_grid_dims_property_order_is_rows_then_columns(self) -> None:
        result = GridTransformSettingsResult(rows=6, columns=9)
        self.assertEqual((6, 9), result.grid_dims)


if __name__ == "__main__":
    unittest.main()
