from enum import Enum
from typing import NamedTuple, Optional

from PyQt6.QtWidgets import (
    QDialog, QWidget, QHBoxLayout, QGridLayout, QLabel, QSpinBox, QPushButton, QComboBox,
    QDoubleSpinBox, QGroupBox, QVBoxLayout,
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


class GridDivisionMode(Enum):
    """How grid division parameters were chosen for convert-to-grid."""

    SPACING = "spacing"
    DIMS = "dims"


class GridDivisionSettingsResult(NamedTuple):
    """Grid division parameters for rigid/mesh-to-grid conversion."""

    mode: GridDivisionMode
    spacing_y: int
    spacing_x: int
    dims_rows: int
    dims_cols: int


class ConvertToGridDialog(QDialog):
    """Prompt for grid spacing or grid dimensions when converting to a grid transform."""

    _DEFAULT_SPACINGS: list[int] = [128, 192, 256, 384, 512, 768]

    def __init__(self, parent=None, defaults: GridRefineDefaults | None = None, **kwargs):
        super().__init__(parent, **kwargs)
        if defaults is None:
            defaults = GridRefineDefaults()

        self._result: GridDivisionSettingsResult | None = None
        self.setWindowTitle("Convert to Grid")

        layout = QVBoxLayout(self)

        spacing_group = QGroupBox("By spacing (distance between control points)", self)
        spacing_layout = QGridLayout(spacing_group)
        self._spacing_y_ctrl = QComboBox(spacing_group)
        self._spacing_x_ctrl = QComboBox(spacing_group)
        for combo in (self._spacing_y_ctrl, self._spacing_x_ctrl):
            for value in self._DEFAULT_SPACINGS:
                combo.addItem(str(value))
        RefineGridSettingsDialog._set_combo_value(self._spacing_y_ctrl, defaults.grid_spacing)
        RefineGridSettingsDialog._set_combo_value(self._spacing_x_ctrl, defaults.grid_spacing)
        spacing_layout.addWidget(QLabel("Y spacing", spacing_group), 0, 0)
        spacing_layout.addWidget(self._spacing_y_ctrl, 0, 1)
        spacing_layout.addWidget(QLabel("X spacing", spacing_group), 1, 0)
        spacing_layout.addWidget(self._spacing_x_ctrl, 1, 1)
        self._convert_spacing_btn = QPushButton("Convert by spacing", spacing_group)
        self._convert_spacing_btn.clicked.connect(self._accept_spacing)
        spacing_layout.addWidget(self._convert_spacing_btn, 2, 0, 1, 2)
        layout.addWidget(spacing_group)

        dims_group = QGroupBox("By dimensions (number of grid points)", self)
        dims_layout = QGridLayout(dims_group)
        self._dims_rows_ctrl = QSpinBox(dims_group)
        self._dims_rows_ctrl.setMinimum(2)
        self._dims_rows_ctrl.setMaximum(512)
        self._dims_rows_ctrl.setValue(8)
        self._dims_cols_ctrl = QSpinBox(dims_group)
        self._dims_cols_ctrl.setMinimum(2)
        self._dims_cols_ctrl.setMaximum(512)
        self._dims_cols_ctrl.setValue(8)
        dims_layout.addWidget(QLabel("Rows (Y)", dims_group), 0, 0)
        dims_layout.addWidget(self._dims_rows_ctrl, 0, 1)
        dims_layout.addWidget(QLabel("Columns (X)", dims_group), 1, 0)
        dims_layout.addWidget(self._dims_cols_ctrl, 1, 1)
        self._convert_dims_btn = QPushButton("Convert by dimensions", dims_group)
        self._convert_dims_btn.clicked.connect(self._accept_dims)
        dims_layout.addWidget(self._convert_dims_btn, 2, 0, 1, 2)
        layout.addWidget(dims_group)

        cancel_btn = QPushButton("Cancel", self)
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(cancel_btn)

        layout.setContentsMargins(15, 15, 15, 15)

    def _accept_spacing(self) -> None:
        self._result = GridDivisionSettingsResult(
            mode=GridDivisionMode.SPACING,
            spacing_y=int(self._spacing_y_ctrl.currentText()),
            spacing_x=int(self._spacing_x_ctrl.currentText()),
            dims_rows=0,
            dims_cols=0,
        )
        self.accept()

    def _accept_dims(self) -> None:
        self._result = GridDivisionSettingsResult(
            mode=GridDivisionMode.DIMS,
            spacing_y=0,
            spacing_x=0,
            dims_rows=self._dims_rows_ctrl.value(),
            dims_cols=self._dims_cols_ctrl.value(),
        )
        self.accept()

    @property
    def division_result(self) -> GridDivisionSettingsResult | None:
        return self._result

    @staticmethod
    def GetGridDivisionSettings(
            parent: Optional[QWidget] = None,
            app_settings: AppSettings | None = None,
    ) -> Optional[GridDivisionSettingsResult]:
        """Prompt for grid spacing or dimensions when converting to a grid transform."""
        defaults = app_settings.stos.grid_refine if app_settings is not None else None
        dlg = ConvertToGridDialog(parent, defaults=defaults)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None
        result = dlg.division_result
        if result is None:
            return None
        if app_settings is not None and result.mode == GridDivisionMode.SPACING:
            app_settings.stos.grid_refine = GridRefineDefaults(
                cell_size=result.spacing_y,
                grid_spacing=result.spacing_y,
            )
        return result


class RefineGridSettingsDialog(QDialog):
    """
    A dialog for configuring grid refinement settings.
    This is the Qt equivalent of the wx RefineGridSettingsDialog.
    """

    _CELL_SIZES: list[int] = [256, 512, 1024]
    _CELL_SPACINGS: list[int] = [128, 192, 256, 384, 512, 768]
    _fixed_num_iterations: int | None
    _conversion_only: bool

    @property
    def cell_size(self) -> int:
        return int(self.cell_size_ctrl.currentText())

    @property
    def grid_spacing(self) -> int:
        return int(self.cell_spacing_ctrl.currentText())

    @property
    def iterations(self) -> int:
        if self._fixed_num_iterations is not None:
            return self._fixed_num_iterations
        return self.iterations_ctrl.value()

    @property
    def max_angle(self) -> float:
        return self.max_angle_ctrl.value()

    @property
    def angle_step_size(self) -> float:
        return self.angle_step_size_ctrl.value()

    def __init__(self, parent=None, defaults: GridRefineDefaults | None = None,
                 conversion_only: bool = False,
                 fixed_num_iterations: int | None = None, **kwargs):
        super(RefineGridSettingsDialog, self).__init__(parent, **kwargs)

        if defaults is None:
            defaults = GridRefineDefaults()

        self._conversion_only = conversion_only
        self._fixed_num_iterations = fixed_num_iterations

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
        title_text = "Grid Division Settings" if conversion_only else "Refine Grid Settings"
        title = QLabel(title_text, panel)
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
        next_row = 3
        if not conversion_only:
            if self._fixed_num_iterations is None:
                grid_layout.addWidget(iterations_label, next_row, 0)
                grid_layout.addWidget(self.iterations_ctrl, next_row, 1)
                next_row += 1
            else:
                iterations_label.hide()
                self.iterations_ctrl.hide()
            grid_layout.addWidget(max_angle_label, next_row, 0)
            grid_layout.addWidget(self.max_angle_ctrl, next_row, 1)
            next_row += 1
            grid_layout.addWidget(angle_step_size_label, next_row, 0)
            grid_layout.addWidget(self.angle_step_size_ctrl, next_row, 1)
            next_row += 1
        else:
            iterations_label.hide()
            self.iterations_ctrl.hide()
            max_angle_label.hide()
            self.max_angle_ctrl.hide()
            angle_step_size_label.hide()
            self.angle_step_size_ctrl.hide()
        grid_layout.addWidget(self.ok_btn, next_row, 0)
        grid_layout.addWidget(self.cancel_btn, next_row, 1)

        # Set the stretch factors for the grid
        grid_layout.setColumnStretch(0, 1)
        grid_layout.setRowStretch(next_row, 1)

        # Set the layout margins
        main_layout.setContentsMargins(15, 15, 15, 15)

        # Set window title
        self.setWindowTitle(title_text)

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
            fixed_num_iterations: int | None = None,
    ) -> Optional[GridSettingsDialogResult]:
        """
        Static method to create and show the dialog, returning the result if OK was clicked.

        Args:
            parent: The parent widget for the dialog
            app_settings: Optional AppSettings to seed from and write back on accept
            fixed_num_iterations: When set, hide the iterations spinner, return this
                value, and do not persist ``num_iterations`` into app settings.

        Returns:
            GridSettingsDialogResult if OK was clicked, None otherwise
        """
        defaults = app_settings.stos.grid_refine if app_settings is not None else None
        dlg = RefineGridSettingsDialog(
            parent, defaults=defaults, fixed_num_iterations=fixed_num_iterations)
        result = dlg.exec()

        if result == QDialog.DialogCode.Accepted:
            if app_settings is not None:
                previous = app_settings.stos.grid_refine
                app_settings.stos.grid_refine = GridRefineDefaults(
                    cell_size=dlg.cell_size,
                    grid_spacing=dlg.grid_spacing,
                    num_iterations=(
                        previous.num_iterations if fixed_num_iterations is not None
                        else dlg.iterations),
                    max_angle=dlg.max_angle,
                    angle_step_size=dlg.angle_step_size,
                )
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
