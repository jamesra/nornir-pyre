from typing import NamedTuple, Optional

from PyQt6.QtWidgets import QDialog, QWidget, QHBoxLayout, QGridLayout, QLabel, QSpinBox, QPushButton


class GridTransformSettingsResult(NamedTuple):
    """User-selected dimensions for a new grid transform."""
    rows: int
    columns: int

    @property
    def grid_dims(self) -> tuple[int, int]:
        """Return (rows, columns) for ITKGridDivision."""
        return self.rows, self.columns


class GridTransformSettingsDialog(QDialog):
    """
    A dialog for configuring grid transform settings.
    This is the Qt equivalent of the wx GridTransformSettingsDialog.
    """
    
    @property
    def columns(self):
        return self.width_ctrl.value()
    
    @property
    def rows(self):
        return self.height_ctrl.value()
    
    @property
    def grid_dims(self):
        return self.rows, self.columns
    
    def __init__(self, parent=None, **kwargs):
        super(GridTransformSettingsDialog, self).__init__(parent, **kwargs)
        
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
        title = QLabel("Grid transform Settings", panel)
        width_label = QLabel("Columns", panel)
        height_label = QLabel("Rows", panel)
        
        # Create the spin boxes
        self.width_ctrl = QSpinBox(panel)
        self.width_ctrl.setMinimum(2)
        self.width_ctrl.setValue(8)
        
        self.height_ctrl = QSpinBox(panel)
        self.height_ctrl.setMinimum(2)
        self.height_ctrl.setValue(8)
        
        # Create the buttons
        self.ok_btn = QPushButton("OK", panel)
        self.ok_btn.clicked.connect(self.accept)
        
        self.cancel_btn = QPushButton("Cancel", panel)
        self.cancel_btn.clicked.connect(self.reject)
        
        # Add widgets to the grid layout
        grid_layout.addWidget(title, 0, 0)
        grid_layout.addWidget(blank, 0, 1)
        grid_layout.addWidget(width_label, 1, 0)
        grid_layout.addWidget(self.width_ctrl, 1, 1)
        grid_layout.addWidget(height_label, 2, 0)
        grid_layout.addWidget(self.height_ctrl, 2, 1)
        grid_layout.addWidget(self.ok_btn, 3, 0)
        grid_layout.addWidget(self.cancel_btn, 3, 1)
        
        # Set the stretch factors for the grid
        grid_layout.setRowStretch(2, 1)
        grid_layout.setColumnStretch(1, 1)
        
        # Set the layout margins
        main_layout.setContentsMargins(15, 15, 15, 15)
        
        # Set window title
        self.setWindowTitle("Grid Transform Settings")
        self.setModal(True)

    @staticmethod
    def GetGridTransformSettings(parent: Optional[QWidget] = None) -> Optional[GridTransformSettingsResult]:
        """Show the dialog and return grid dimensions when the user accepts."""
        dlg = GridTransformSettingsDialog(parent)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None
        return GridTransformSettingsResult(rows=dlg.rows, columns=dlg.columns)
