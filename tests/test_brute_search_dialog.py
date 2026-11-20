"""Rotate/Translate > Brute Force asks how much to search and keeps the answer (James, 2026-11-20)."""

from __future__ import annotations

import unittest
from unittest import mock

import numpy as np
from nornir_imageregistration.settings import SliceToSliceMethod
from nornir_imageregistration.settings.stos_brute import StosBruteSettings
from PyQt6.QtWidgets import QApplication, QDialog

from pyre.settings.app import AppSettings, BruteSearchDefaults
from pyre.ui.windows import brute_search_dialog
from pyre.ui.windows.brute_search_dialog import (
    BruteSearchDialog,
    brute_settings_from,
    search_size_text,
)


class TestBruteSettingsFromSearch(unittest.TestCase):

    def test_the_defaults_search_the_full_circle_every_2_degrees_at_818_px(self) -> None:
        base = StosBruteSettings(method=SliceToSliceMethod.LogPolar, larget_dimension=1024)
        working = brute_settings_from(BruteSearchDefaults(), base)
        self.assertEqual(SliceToSliceMethod.BruteForce, working.method)
        self.assertEqual(180, len(working.angle_range))
        self.assertTrue(working.search_scale)
        self.assertTrue(working.try_flipped)
        self.assertEqual(818, working.larget_dimension)
        self.assertEqual(SliceToSliceMethod.LogPolar, base.method, "the stored settings are not changed")
        self.assertEqual(1024, base.larget_dimension)

    def test_a_narrow_search(self) -> None:
        search = BruteSearchDefaults(full_circle=False, max_angle=10.0, angle_step_size=5.0,
                                     search_scale=False, try_flipped=False, min_overlap=0.5,
                                     largest_dimension=512)
        working = brute_settings_from(search, StosBruteSettings())
        np.testing.assert_array_equal([-10.0, -5.0, 0.0, 5.0, 10.0], working.angle_range)
        self.assertFalse(working.search_scale)
        self.assertFalse(working.try_flipped)
        self.assertEqual(0.5, working.min_overlap)
        self.assertEqual(512, working.larget_dimension)
        self.assertEqual("1 sweep of 5 angles (5 scores), then a refine", search_size_text(search))

    def test_the_size_counts_scales_and_flip(self) -> None:
        self.assertEqual("22 sweeps of 180 angles (3960 scores), then a refine",
                         search_size_text(BruteSearchDefaults()))


class TestBruteSearchDialog(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_defaults_button_restores_the_original_search(self) -> None:
        dialog = BruteSearchDialog(BruteSearchDefaults(full_circle=False, search_scale=False))
        dialog._load(BruteSearchDefaults())
        self.assertEqual(BruteSearchDefaults(), dialog.search())
        self.assertFalse(dialog._max_angle.isEnabled())

    def test_ok_saves_the_choice_for_the_next_run(self) -> None:
        settings = AppSettings()
        chosen = BruteSearchDefaults(full_circle=False, max_angle=20.0, try_flipped=False)
        with mock.patch.object(BruteSearchDialog, 'exec', return_value=QDialog.DialogCode.Accepted), \
                mock.patch.object(BruteSearchDialog, 'search', return_value=chosen), \
                mock.patch.object(brute_search_dialog, 'save_app_settings') as save:
            working = BruteSearchDialog.ask(settings)
        self.assertEqual(chosen, settings.stos.brute_search)
        save.assert_called_once_with(settings)
        self.assertIsNotNone(working)
        self.assertFalse(working.try_flipped)

    def test_cancel_runs_nothing_and_saves_nothing(self) -> None:
        settings = AppSettings()
        with mock.patch.object(BruteSearchDialog, 'exec', return_value=QDialog.DialogCode.Rejected), \
                mock.patch.object(brute_search_dialog, 'save_app_settings') as save:
            self.assertIsNone(BruteSearchDialog.ask(settings))
        save.assert_not_called()
        self.assertEqual(BruteSearchDefaults(), settings.stos.brute_search)


if __name__ == '__main__':
    unittest.main()
