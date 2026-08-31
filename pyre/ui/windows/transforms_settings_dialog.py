"""Tabbed dialog for editing per-transform registration defaults in AppSettings."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from nornir_imageregistration.settings import SliceToSliceMethod
from nornir_imageregistration.settings.stos_brute import StosBruteSettings

from pyre.settings.app import (
    AngleSearchRange,
    AppSettings,
    GridRefineDefaults,
    PointRegistrationSettings,
)


class TransformsSettingsDialog(QDialog):
    """Edit Rigid, Grid, and Point/Mesh registration defaults on AppSettings."""

    _CELL_SIZES: list[int] = [256, 512, 1024]
    _CELL_SPACINGS: list[int] = [128, 192, 256, 384, 512, 768]
    _ALIGNMENT_AREAS: list[int] = [64, 128, 256, 512]

    def __init__(self, settings: AppSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self.setWindowTitle("Transform Settings")
        self.setMinimumWidth(420)

        tabs = QTabWidget(self)
        tabs.addTab(self._build_rigid_tab(settings.stos.brute_registration), "Rigid")
        tabs.addTab(self._build_grid_tab(settings.stos.grid_refine), "Grid")
        tabs.addTab(self._build_point_tab(settings.stos.point_registration), "Point / Mesh")

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        layout.addWidget(buttons)

    def _build_rigid_tab(self, brute: StosBruteSettings) -> QWidget:
        """Build controls for stos.brute_registration."""
        page = QWidget(self)
        form = QFormLayout(page)

        self._try_flipped = QCheckBox("Check for flipped sections", page)
        self._try_flipped.setChecked(bool(brute.try_flipped))
        form.addRow(self._try_flipped)

        self._method = QComboBox(page)
        self._method.addItem("Log Polar", SliceToSliceMethod.LogPolar)
        self._method.addItem("Brute Force", SliceToSliceMethod.BruteForce)
        method_index = 0 if brute.method == SliceToSliceMethod.LogPolar else 1
        self._method.setCurrentIndex(method_index)
        form.addRow("Default method", self._method)

        self._min_overlap = QDoubleSpinBox(page)
        self._min_overlap.setRange(0.05, 1.0)
        self._min_overlap.setSingleStep(0.05)
        self._min_overlap.setDecimals(2)
        self._min_overlap.setValue(float(brute.min_overlap))
        form.addRow("Min overlap", self._min_overlap)

        self._largest_dimension = QSpinBox(page)
        self._largest_dimension.setRange(64, 8192)
        self._largest_dimension.setSingleStep(64)
        largest = brute.larget_dimension if brute.larget_dimension is not None else 1024
        self._largest_dimension.setValue(int(largest))
        form.addRow("Largest dimension", self._largest_dimension)

        return page

    def _build_grid_tab(self, defaults: GridRefineDefaults) -> QWidget:
        """Build controls for stos.grid_refine."""
        page = QWidget(self)
        form = QFormLayout(page)

        self._cell_size = QComboBox(page)
        for size in self._CELL_SIZES:
            self._cell_size.addItem(str(size))
        self._set_combo_value(self._cell_size, defaults.cell_size)

        self._grid_spacing = QComboBox(page)
        for spacing in self._CELL_SPACINGS:
            self._grid_spacing.addItem(str(spacing))
        self._set_combo_value(self._grid_spacing, defaults.grid_spacing)

        self._num_iterations = QSpinBox(page)
        self._num_iterations.setMinimum(2)
        self._num_iterations.setMaximum(100)
        self._num_iterations.setValue(defaults.num_iterations)

        self._grid_max_angle = QDoubleSpinBox(page)
        self._grid_max_angle.setRange(0.0, 180.0)
        self._grid_max_angle.setSingleStep(2.0)
        self._grid_max_angle.setValue(defaults.max_angle)

        self._grid_angle_step = QDoubleSpinBox(page)
        self._grid_angle_step.setRange(0.5, 180.0)
        self._grid_angle_step.setSingleStep(0.5)
        self._grid_angle_step.setValue(defaults.angle_step_size)

        form.addRow("Cell size", self._cell_size)
        form.addRow("Grid spacing", self._grid_spacing)
        form.addRow("# of iterations", self._num_iterations)
        form.addRow("Max angle (± degrees)", self._grid_max_angle)
        form.addRow("Angle step (degrees)", self._grid_angle_step)
        return page

    def _build_point_tab(self, point: PointRegistrationSettings) -> QWidget:
        """Build controls for stos.point_registration."""
        page = QWidget(self)
        form = QFormLayout(page)

        self._alignment_area = QComboBox(page)
        for size in self._ALIGNMENT_AREAS:
            self._alignment_area.addItem(str(size))
        self._set_combo_value(self._alignment_area, point.alignment_area)

        angle = point.angle_search_range
        self._point_max_angle = QDoubleSpinBox(page)
        self._point_max_angle.setRange(0.0, 180.0)
        self._point_max_angle.setSingleStep(1.0)
        self._point_max_angle.setValue(float(angle.max_angle))

        self._point_angle_step = QDoubleSpinBox(page)
        self._point_angle_step.setRange(0.5, 180.0)
        self._point_angle_step.setSingleStep(0.5)
        self._point_angle_step.setValue(float(angle.angle_step_size))

        form.addRow("Alignment area", self._alignment_area)
        form.addRow("Max angle (± degrees)", self._point_max_angle)
        form.addRow("Angle step (degrees)", self._point_angle_step)
        return page

    @staticmethod
    def _set_combo_value(combo: QComboBox, value: int) -> None:
        """Select *value* in *combo*, inserting it when missing."""
        text = str(value)
        index = combo.findText(text)
        if index < 0:
            combo.addItem(text)
            index = combo.findText(text)
        combo.setCurrentIndex(index if index >= 0 else 0)

    def apply_to_settings(self) -> None:
        """Write dialog values into the live AppSettings object."""
        brute = self._settings.stos.brute_registration
        brute.try_flipped = self._try_flipped.isChecked()
        brute.method = self._method.currentData()
        brute.min_overlap = float(self._min_overlap.value())
        brute.larget_dimension = int(self._largest_dimension.value())

        self._settings.stos.grid_refine = GridRefineDefaults(
            cell_size=int(self._cell_size.currentText()),
            grid_spacing=int(self._grid_spacing.currentText()),
            num_iterations=int(self._num_iterations.value()),
            max_angle=float(self._grid_max_angle.value()),
            angle_step_size=float(self._grid_angle_step.value()),
        )

        self._settings.stos.point_registration = PointRegistrationSettings(
            alignment_area=int(self._alignment_area.currentText()),
            angle_search_range=AngleSearchRange(
                max_angle=float(self._point_max_angle.value()),
                angle_step_size=float(self._point_angle_step.value()),
            ),
        )

    @staticmethod
    def edit_settings(settings: AppSettings, parent: QWidget | None = None) -> bool:
        """Show the dialog; return True if the user accepted and settings were applied."""
        dlg = TransformsSettingsDialog(settings, parent)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return False
        dlg.apply_to_settings()
        return True
