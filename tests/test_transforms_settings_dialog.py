"""Tests for Settings → Transforms registration defaults dialog and flip default."""

from __future__ import annotations

import sys
import unittest
from unittest.mock import patch

from PyQt6.QtWidgets import QApplication, QDialog

from nornir_imageregistration.settings import SliceToSliceMethod
from nornir_imageregistration.settings.stos_brute import StosBruteSettings

from pyre.settings.app import AppSettings, GridRefineDefaults
from pyre.ui.windows.refine_grid_settings_dialog import (
    ConvertToGridDialog,
    GridDivisionMode,
    RefineGridSettingsDialog,
)
from pyre.ui.windows.transforms_settings_dialog import TransformsSettingsDialog


class TestTryFlippedDefault(unittest.TestCase):
    def test_stos_brute_settings_try_flipped_defaults_true(self) -> None:
        settings = StosBruteSettings(method=SliceToSliceMethod.LogPolar)
        self.assertTrue(settings.try_flipped)

    def test_app_settings_brute_registration_try_flipped_defaults_true(self) -> None:
        app = AppSettings()
        self.assertTrue(app.stos.brute_registration.try_flipped)


class TestTransformsSettingsDialog(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication(sys.argv)

    def test_dialog_loads_current_settings(self) -> None:
        settings = AppSettings()
        settings.stos.brute_registration.try_flipped = False
        settings.stos.brute_registration.min_overlap = 0.4
        settings.stos.grid_refine = GridRefineDefaults(cell_size=512, grid_spacing=256, num_iterations=7)
        settings.stos.point_registration.alignment_area = 128

        dlg = TransformsSettingsDialog(settings)
        self.assertFalse(dlg._try_flipped.isChecked())
        self.assertAlmostEqual(0.4, dlg._min_overlap.value())
        self.assertEqual("512", dlg._cell_size.currentText())
        self.assertEqual("256", dlg._grid_spacing.currentText())
        self.assertEqual(7, dlg._num_iterations.value())
        self.assertEqual("128", dlg._alignment_area.currentText())

    def test_apply_to_settings_updates_try_flipped_and_tabs(self) -> None:
        settings = AppSettings()
        settings.stos.brute_registration.try_flipped = True

        dlg = TransformsSettingsDialog(settings)
        dlg._try_flipped.setChecked(False)
        dlg._min_overlap.setValue(0.55)
        dlg._largest_dimension.setValue(1024)
        dlg._method.setCurrentIndex(1)  # Brute Force
        dlg._set_combo_value(dlg._cell_size, 1024)
        dlg._set_combo_value(dlg._grid_spacing, 384)
        dlg._num_iterations.setValue(9)
        dlg._grid_max_angle.setValue(10.0)
        dlg._grid_angle_step.setValue(2.5)
        dlg._set_combo_value(dlg._alignment_area, 512)
        dlg._point_max_angle.setValue(4.0)
        dlg._point_angle_step.setValue(1.0)
        dlg.apply_to_settings()

        self.assertFalse(settings.stos.brute_registration.try_flipped)
        self.assertAlmostEqual(0.55, settings.stos.brute_registration.min_overlap)
        self.assertEqual(1024, settings.stos.brute_registration.larget_dimension)
        self.assertEqual(SliceToSliceMethod.BruteForce, settings.stos.brute_registration.method)
        self.assertEqual(1024, settings.stos.grid_refine.cell_size)
        self.assertEqual(384, settings.stos.grid_refine.grid_spacing)
        self.assertEqual(9, settings.stos.grid_refine.num_iterations)
        self.assertAlmostEqual(10.0, settings.stos.grid_refine.max_angle)
        self.assertAlmostEqual(2.5, settings.stos.grid_refine.angle_step_size)
        self.assertEqual(512, settings.stos.point_registration.alignment_area)
        self.assertAlmostEqual(4.0, settings.stos.point_registration.angle_search_range.max_angle)

    def test_edit_settings_applies_only_when_accepted(self) -> None:
        settings = AppSettings()
        settings.stos.brute_registration.try_flipped = True

        with patch.object(TransformsSettingsDialog, "exec", return_value=QDialog.DialogCode.Rejected):
            self.assertFalse(TransformsSettingsDialog.edit_settings(settings))
        self.assertTrue(settings.stos.brute_registration.try_flipped)

        def accept_and_uncheck_flip(self):
            self._try_flipped.setChecked(False)
            return QDialog.DialogCode.Accepted

        with patch.object(TransformsSettingsDialog, "exec", accept_and_uncheck_flip):
            self.assertTrue(TransformsSettingsDialog.edit_settings(settings))
        self.assertFalse(settings.stos.brute_registration.try_flipped)


class TestRefineGridSettingsDialogPersistence(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication(sys.argv)

    def test_seeds_from_app_settings_and_writes_back(self) -> None:
        settings = AppSettings()
        settings.stos.grid_refine = GridRefineDefaults(
            cell_size=512,
            grid_spacing=256,
            num_iterations=8,
            max_angle=6.0,
            angle_step_size=1.5,
        )

        with patch.object(RefineGridSettingsDialog, "exec", return_value=QDialog.DialogCode.Accepted):
            result = RefineGridSettingsDialog.GetGridRefineSettings(app_settings=settings)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(512, result.cell_size)
        self.assertEqual(256, result.grid_spacing)
        self.assertEqual(8, result.num_iterations)
        self.assertEqual(512, settings.stos.grid_refine.cell_size)
        self.assertEqual(256, settings.stos.grid_refine.grid_spacing)
        self.assertEqual(8, settings.stos.grid_refine.num_iterations)

    def test_convert_dialog_spacing_mode(self) -> None:
        dlg = ConvertToGridDialog()
        RefineGridSettingsDialog._set_combo_value(dlg._spacing_y_ctrl, 256)
        RefineGridSettingsDialog._set_combo_value(dlg._spacing_x_ctrl, 384)
        dlg._accept_spacing()
        result = dlg.division_result
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(GridDivisionMode.SPACING, result.mode)
        self.assertEqual(256, result.spacing_y)
        self.assertEqual(384, result.spacing_x)

    def test_convert_dialog_dims_mode(self) -> None:
        dlg = ConvertToGridDialog()
        dlg._dims_rows_ctrl.setValue(10)
        dlg._dims_cols_ctrl.setValue(12)
        dlg._accept_dims()
        result = dlg.division_result
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(GridDivisionMode.DIMS, result.mode)
        self.assertEqual(10, result.dims_rows)
        self.assertEqual(12, result.dims_cols)

    def test_grid_division_settings_cancelled(self) -> None:
        with patch.object(ConvertToGridDialog, "exec", return_value=QDialog.DialogCode.Rejected):
            result = ConvertToGridDialog.GetGridDivisionSettings()
        self.assertIsNone(result)

    def test_fixed_num_iterations_hides_spinner_and_returns_one(self) -> None:
        defaults = GridRefineDefaults(num_iterations=8, cell_size=512, grid_spacing=256)
        dlg = RefineGridSettingsDialog(defaults=defaults, fixed_num_iterations=1)
        self.assertTrue(dlg.iterations_ctrl.isHidden())
        self.assertEqual(1, dlg.iterations)
        self.assertEqual(512, dlg.cell_size)

    def test_fixed_num_iterations_does_not_clobber_stored_iterations(self) -> None:
        settings = AppSettings()
        settings.stos.grid_refine = GridRefineDefaults(
            cell_size=512,
            grid_spacing=256,
            num_iterations=8,
            max_angle=6.0,
            angle_step_size=1.5,
        )

        def accept_and_change_size(self: RefineGridSettingsDialog) -> QDialog.DialogCode:
            RefineGridSettingsDialog._set_combo_value(self.cell_size_ctrl, 1024)
            RefineGridSettingsDialog._set_combo_value(self.cell_spacing_ctrl, 384)
            return QDialog.DialogCode.Accepted

        with patch.object(RefineGridSettingsDialog, "exec", accept_and_change_size):
            result = RefineGridSettingsDialog.GetGridRefineSettings(
                app_settings=settings, fixed_num_iterations=1)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(1, result.num_iterations)
        self.assertEqual(1024, result.cell_size)
        self.assertEqual(384, result.grid_spacing)
        self.assertEqual(1024, settings.stos.grid_refine.cell_size)
        self.assertEqual(384, settings.stos.grid_refine.grid_spacing)
        self.assertEqual(8, settings.stos.grid_refine.num_iterations)

    def test_fixed_num_iterations_cancelled_does_not_persist(self) -> None:
        settings = AppSettings()
        settings.stos.grid_refine = GridRefineDefaults(
            cell_size=512, grid_spacing=256, num_iterations=8)
        with patch.object(RefineGridSettingsDialog, "exec", return_value=QDialog.DialogCode.Rejected):
            result = RefineGridSettingsDialog.GetGridRefineSettings(
                app_settings=settings, fixed_num_iterations=1)
        self.assertIsNone(result)
        self.assertEqual(512, settings.stos.grid_refine.cell_size)
        self.assertEqual(8, settings.stos.grid_refine.num_iterations)


if __name__ == "__main__":
    unittest.main()
