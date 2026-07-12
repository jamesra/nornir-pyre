from typing import NamedTuple, Optional

from PyQt6.QtWidgets import (
    QDialog, QWidget, QHBoxLayout, QGridLayout, QLabel, QSpinBox, QPushButton, QComboBox,
    QDoubleSpinBox,
)

import nornir_imageregistration.settings
import pyre.settings
from pyre.settings.app import AppSettings, GridRefineDefaults


class GridSettingsDialogResult(NamedTuple):
    num_iterations: int
    cell_size: int
    grid_spacing: int
    angle_range: pyre.settings.AngleSearchRange

    @property
    def angles_to_search(self) -> list[float]:
        return list(nornir_imageregistration.settings.AngleSearchRange(
            max_angle=getattr(self, 'max_angle', 180),
            angle_step_size=getattr(self, 'angle_step_size', 1.0)).angle_range)


class RefineGridSettingsDialog(QDialog):
    """
    A dialog for configuring grid refinement settings.
    This is the Qt equivalent of the wx RefineGridSettingsDialog.
    """

    _CELL_SIZES: list[int] = [256, 512, 1024]
    _CELL_SPACINGS: list[int] = [128, 192, 256, 384, 512, 768]

    @property
    def cell_size(self) -> int:
        return int(self.cell_size_ctrl.currentText())

    @property
    def grid_spacing(self) -> int:
        return int(self.cell_spacing_ctrl.currentText())

    @property
    def iterations(self) -> int:
        return self.iterations_ctrl.value()

    @property
    def max_angle(self) -> float:
        return self.max_angle_ctrl.value()

    @property
    def angle_step_size(self) -> float:
        return self.angle_step_size_ctrl.value()

    def __init__(self, parent=None, defaults: GridRefineDefaults | None = None, **kwargs):
        super(RefineGridSettingsDialog, self).__init__(parent, **kwargs)

        if defaults is None:
            defaults = GridRefineDefaults()

        # Create the main layout
        main_layout = QHBoxLayout(self)

        # Create a widget to hold the grid layout
        panel = QWidget(self)
        main_layout.addWidget(panel)

        # Create the grid layout
        grid_layout = QGridLayout(panel)
        grid_layout.setSpacing(10)

        # Create a blank widget for spacing
        blank = QWidget(panel)

        # Create the labels
        title = QLabel("Refine Grid Settings", panel)
        cell_size_label = QLabel("Cell Size", panel)
        grid_spacing_label = QLabel("Grid Spacing", panel)
        iterations_label = QLabel("# of Iterations", panel)
        max_angle_label = QLabel("Max Angle, +/- degrees from 0", panel)
        angle_step_size_label = QLabel("Angle step size in degrees, 0 is always included", panel)

        self.cell_size_ctrl = QComboBox(panel)
        for size in self._CELL_SIZES:
            self.cell_size_ctrl.addItem(str(size))
        self._set_combo_value(self.cell_size_ctrl, defaults.cell_size)

        self.cell_spacing_ctrl = QComboBox(panel)
        for spacing in self._CELL_SPACINGS:
            self.cell_spacing_ctrl.addItem(str(spacing))
        self._set_combo_value(self.cell_spacing_ctrl, defaults.grid_spacing)

        self.iterations_ctrl = QSpinBox(panel)
        self.iterations_ctrl.setMinimum(2)
        self.iterations_ctrl.setValue(defaults.num_iterations)

        self.max_angle_ctrl = QDoubleSpinBox(panel)
        self.max_angle_ctrl.setMinimum(0)
        self.max_angle_ctrl.setMaximum(180)
        self.max_angle_ctrl.setValue(defaults.max_angle)
        self.max_angle_ctrl.setSingleStep(2)

        self.angle_step_size_ctrl = QDoubleSpinBox(panel)
        self.angle_step_size_ctrl.setMinimum(0.5)
        self.angle_step_size_ctrl.setMaximum(180)
        self.angle_step_size_ctrl.setValue(defaults.angle_step_size)
        self.angle_step_size_ctrl.setSingleStep(0.5)

        # Create the buttons
        self.ok_btn = QPushButton("OK", panel)
        self.ok_btn.clicked.connect(self.accept)

        self.cancel_btn = QPushButton("Cancel", panel)
        self.cancel_btn.clicked.connect(self.reject)

        # Add widgets to the grid layout
        grid_layout.addWidget(title, 0, 0)
        grid_layout.addWidget(blank, 0, 1)
        grid_layout.addWidget(cell_size_label, 1, 0)
        grid_layout.addWidget(self.cell_size_ctrl, 1, 1)
        grid_layout.addWidget(grid_spacing_label, 2, 0)
        grid_layout.addWidget(self.cell_spacing_ctrl, 2, 1)
        grid_layout.addWidget(iterations_label, 3, 0)
        grid_layout.addWidget(self.iterations_ctrl, 3, 1)
        grid_layout.addWidget(max_angle_label, 4, 0)
        grid_layout.addWidget(self.max_angle_ctrl, 4, 1)
        grid_layout.addWidget(angle_step_size_label, 5, 0)
        grid_layout.addWidget(self.angle_step_size_ctrl, 5, 1)
        grid_layout.addWidget(self.ok_btn, 6, 0)
        grid_layout.addWidget(self.cancel_btn, 6, 1)

        # Set the stretch factors for the grid
        grid_layout.setColumnStretch(0, 1)
        grid_layout.setRowStretch(6, 1)

        # Set the layout margins
        main_layout.setContentsMargins(15, 15, 15, 15)

        # Set window title
        self.setWindowTitle("Refine Grid Settings")

    @staticmethod
    def _set_combo_value(combo: QComboBox, value: int) -> None:
        """Select *value* in *combo*, inserting it when missing."""
        text = str(value)
        index = combo.findText(text)
        if index < 0:
            combo.addItem(text)
            index = combo.findText(text)
        combo.setCurrentIndex(index if index >= 0 else 0)

    def to_defaults(self) -> GridRefineDefaults:
        """Capture the current dialog controls as GridRefineDefaults."""
        return GridRefineDefaults(
            cell_size=self.cell_size,
            grid_spacing=self.grid_spacing,
            num_iterations=self.iterations,
            max_angle=self.max_angle,
            angle_step_size=self.angle_step_size,
        )

    @staticmethod
    def GetGridRefineSettings(
            parent: Optional[QWidget] = None,
            app_settings: AppSettings | None = None,
    ) -> Optional[GridSettingsDialogResult]:
        """
        Static method to create and show the dialog, returning the result if OK was clicked.

        Args:
            parent: The parent widget for the dialog
            app_settings: Optional AppSettings to seed from and write back on accept

        Returns:
            GridSettingsDialogResult if OK was clicked, None otherwise
        """
        defaults = app_settings.stos.grid_refine if app_settings is not None else None
        dlg = RefineGridSettingsDialog(parent, defaults=defaults)
        result = dlg.exec()

        if result == QDialog.DialogCode.Accepted:
            if app_settings is not None:
                app_settings.stos.grid_refine = dlg.to_defaults()
            return GridSettingsDialogResult(
                num_iterations=dlg.iterations,
                cell_size=dlg.cell_size,
                grid_spacing=dlg.grid_spacing,
                angle_range=pyre.settings.AngleSearchRange(
                    max_angle=dlg.max_angle,
                    angle_step_size=dlg.angle_step_size)
            )
        else:
            return None
