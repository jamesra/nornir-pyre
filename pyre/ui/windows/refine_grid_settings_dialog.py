from typing import NamedTuple

import wx
from wx.lib.agw.floatspin import FloatSpin
import nornir_imageregistration.settings
import pyre.state
import pyre.settings


class GridSettingsDialogResult(NamedTuple):
    num_iterations: int
    cell_size: int
    grid_spacing: int
    angle_range: pyre.settings.AngleSearchRange

    @property
    def angles_to_search(self) -> list[float]:
        return nornir_imageregistration.settings.AngleSearchRange(max_angle=self.max_angle,
                                                                  angle_step_size=self.angle_step_size).angle_range


class RefineGridSettingsDialog(wx.Dialog):

    @property
    def cell_size(self) -> int:
        return int(self.cell_size_ctrl.GetString(self.cell_size_ctrl.GetSelection()))

    @property
    def grid_spacing(self) -> int:
        return int(self.cell_spacing_ctrl.GetString(self.cell_spacing_ctrl.GetSelection()))

    @property
    def iterations(self) -> int:
        return self.iterations_ctrl.GetValue()

    @property
    def max_angle(self) -> int:
        return self.max_angle_ctrl.GetValue()

    @property
    def angle_step_size(self) -> int:
        return self.angle_step_size_ctrl.GetValue()

    def __init__(self, parent, **kwargs):
        super(RefineGridSettingsDialog, self).__init__(parent, **kwargs)
        # panel = wx.Panel(self)
        hbox = wx.BoxSizer(wx.HORIZONTAL)
        fgs = wx.FlexGridSizer(7, 2, 10, 10)
        blank = wx.Panel(self)
        panel = self

        title = wx.StaticText(panel, label="Refine Grid Settings")
        cell_size = wx.StaticText(panel, label="Cell Size")
        grid_spacing = wx.StaticText(panel, label="Grid Spacing")
        iterations = wx.StaticText(panel, label="# of Iterations")
        max_angle = wx.StaticText(panel, label="Max Angle, +/- degrees from 0")
        angle_step_size = wx.StaticText(panel, label="Angle step size in degrees, 0 is always included")

        cell_sizes = [256, 512, 1024]
        cell_spacing = [128, 192, 256, 384, 512, 768]
        self.cell_size_ctrl = wx.Choice(panel, choices=list(map(str, cell_sizes)))
        self.cell_size_ctrl.SetSelection(0)
        self.cell_spacing_ctrl = wx.Choice(panel, choices=list(map(str, cell_spacing)))
        self.cell_spacing_ctrl.SetSelection(1)
        self.iterations_ctrl = wx.SpinCtrl(panel, min=2, initial=5)
        self.max_angle_ctrl = FloatSpin(panel, min_val=0, max_val=180, value=5, increment=2)
        self.angle_step_size_ctrl = FloatSpin(panel, min_val=0.5, max_val=180, value=3, increment=0.5)

        self.ok_btn = wx.Button(panel, wx.ID_OK, label="OK")
        self.cancel_btn = wx.Button(panel, wx.ID_OK, label="Cancel")

        fgs.AddMany([title, blank,
                     cell_size, self.cell_size_ctrl,
                     grid_spacing, self.cell_spacing_ctrl,
                     iterations, self.iterations_ctrl,
                     max_angle, self.max_angle_ctrl,
                     angle_step_size, self.angle_step_size_ctrl,
                     self.ok_btn, (self.cancel_btn, 1, wx.EXPAND)])
        fgs.AddGrowableCol(0, 1)
        fgs.AddGrowableRow(6, 1)
        hbox.Add(fgs, proportion=2, flag=wx.ALL | wx.EXPAND, border=15)
        self.SetSizer(hbox)

    @staticmethod
    def GetGridRefineSettings(parent: wx.Window) -> None | GridSettingsDialogResult:
        with RefineGridSettingsDialog(parent) as dlg:
            if dlg.ShowModal() == wx.ID_OK:
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
