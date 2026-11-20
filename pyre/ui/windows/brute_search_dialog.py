"""Dialog for how much Rotate/Translate > Brute Force searches (angles, scales, flip, image size)."""

from __future__ import annotations

from nornir_imageregistration.settings import AngleSearchRange as IrAngleSearchRange
from nornir_imageregistration.settings import SliceToSliceMethod
from nornir_imageregistration.settings.stos_brute import StosBruteSettings
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from pyre.settings.app import AppSettings, BruteSearchDefaults
from pyre.settings.persistence import save_app_settings

# Scale candidates StosBrute sweeps when scale search is on and there is no scale hint
# (stos_brute._SCALE_REFINE_TISSUE_GRID). Only used for the size estimate shown to the user.
SCALES_SEARCHED: int = 11


def brute_settings_from(search: BruteSearchDefaults, base: StosBruteSettings) -> StosBruteSettings:
    """A copy of *base* set to BruteForce with the search the dialog chose."""
    working = base.model_copy()
    working.method = SliceToSliceMethod.BruteForce
    working.angles = IrAngleSearchRange(
        max_angle=None if search.full_circle else float(search.max_angle),
        angle_step_size=float(search.angle_step_size))
    working.search_scale = bool(search.search_scale)
    working.try_flipped = bool(search.try_flipped)
    working.min_overlap = float(search.min_overlap)
    working.larget_dimension = int(search.largest_dimension)
    return working


def search_size_text(search: BruteSearchDefaults) -> str:
    """How many angle sweeps the search runs, and how many angles each one scores."""
    angles = len(IrAngleSearchRange(
        max_angle=None if search.full_circle else float(search.max_angle),
        angle_step_size=float(search.angle_step_size)).angle_range)
    sweeps = (SCALES_SEARCHED if search.search_scale else 1) * (2 if search.try_flipped else 1)
    return f"{sweeps} sweep{'s' if sweeps != 1 else ''} of {angles} angles ({sweeps * angles} scores), then a refine"


class BruteSearchDialog(QDialog):
    """Set how much Brute Force searches. OK saves the choice for the next run; Defaults restores the original search."""

    _full_circle: QCheckBox
    _max_angle: QDoubleSpinBox
    _angle_step: QDoubleSpinBox
    _search_scale: QCheckBox
    _try_flipped: QCheckBox
    _min_overlap: QDoubleSpinBox
    _largest_dimension: QSpinBox
    _size_label: QLabel

    def __init__(self, search: BruteSearchDefaults, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Brute Force Search")
        self.setMinimumWidth(420)
        form = QFormLayout()

        self._full_circle = QCheckBox("Search every angle (full circle)", self)
        self._full_circle.setToolTip("Off: search only +/- the max angle around the current rotation of 0.")
        form.addRow(self._full_circle)

        self._max_angle = QDoubleSpinBox(self)
        self._max_angle.setRange(0.0, 180.0)
        self._max_angle.setSingleStep(5.0)
        self._max_angle.setDecimals(1)
        form.addRow("Max angle, +/- degrees", self._max_angle)

        self._angle_step = QDoubleSpinBox(self)
        self._angle_step.setRange(0.25, 45.0)
        self._angle_step.setSingleStep(0.5)
        self._angle_step.setDecimals(2)
        form.addRow("Angle step, degrees", self._angle_step)

        self._search_scale = QCheckBox("Search scale (11 scales)", self)
        self._search_scale.setToolTip("Off: register at the current scale only, which is about 11x faster.")
        form.addRow(self._search_scale)

        self._try_flipped = QCheckBox("Also search the flipped section", self)
        self._try_flipped.setToolTip("Off: halves the time. Leave on unless you know the section is not flipped.")
        form.addRow(self._try_flipped)

        self._min_overlap = QDoubleSpinBox(self)
        self._min_overlap.setRange(0.05, 1.0)
        self._min_overlap.setSingleStep(0.05)
        self._min_overlap.setDecimals(2)
        form.addRow("Min overlap", self._min_overlap)

        self._largest_dimension = QSpinBox(self)
        self._largest_dimension.setRange(128, 8192)
        self._largest_dimension.setSingleStep(64)
        self._largest_dimension.setToolTip("Images are shrunk so their longest side is this many pixels. "
                                           "Larger is more precise and slower.")
        form.addRow("Image size, px", self._largest_dimension)

        self._size_label = QLabel(self)
        form.addRow("Search size", self._size_label)

        defaults_button = QPushButton("Defaults", self)
        defaults_button.setToolTip("Go back to the original search: every angle every 2 degrees, "
                                   "11 scales, flipped too, 818 px.")
        defaults_button.clicked.connect(lambda: self._load(BruteSearchDefaults()))
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, parent=self)
        buttons.addButton(defaults_button, QDialogButtonBox.ButtonRole.ResetRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

        for box in (self._full_circle, self._search_scale, self._try_flipped):
            box.toggled.connect(self._refresh)
        for spin in (self._max_angle, self._angle_step):
            spin.valueChanged.connect(self._refresh)
        self._load(search)

    def _load(self, search: BruteSearchDefaults) -> None:
        """Show *search* in the controls."""
        self._full_circle.setChecked(bool(search.full_circle))
        self._max_angle.setValue(float(search.max_angle))
        self._angle_step.setValue(float(search.angle_step_size))
        self._search_scale.setChecked(bool(search.search_scale))
        self._try_flipped.setChecked(bool(search.try_flipped))
        self._min_overlap.setValue(float(search.min_overlap))
        self._largest_dimension.setValue(int(search.largest_dimension))
        self._refresh()

    def _refresh(self, *_args: object) -> None:
        self._max_angle.setEnabled(not self._full_circle.isChecked())
        self._size_label.setText(search_size_text(self.search()))

    def search(self) -> BruteSearchDefaults:
        """The search the controls describe."""
        return BruteSearchDefaults(
            full_circle=self._full_circle.isChecked(),
            max_angle=float(self._max_angle.value()),
            angle_step_size=float(self._angle_step.value()),
            search_scale=self._search_scale.isChecked(),
            try_flipped=self._try_flipped.isChecked(),
            min_overlap=float(self._min_overlap.value()),
            largest_dimension=int(self._largest_dimension.value()),
        )

    @staticmethod
    def ask(settings: AppSettings, parent: QWidget | None = None) -> StosBruteSettings | None:
        """Show the dialog; on OK save the choice and return the StosBrute settings to run, else None."""
        dialog = BruteSearchDialog(settings.stos.brute_search, parent)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        settings.stos.brute_search = dialog.search()
        save_app_settings(settings)
        return brute_settings_from(settings.stos.brute_search, settings.stos.brute_registration)
