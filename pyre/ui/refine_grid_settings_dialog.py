import nornir_imageregistration.settings
import wx
import pyre.state

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

    def __init__(self, parent, **kwargs):
        super(RefineGridSettingsDialog, self).__init__(parent, **kwargs)
        panel = wx.Panel(self)
        hbox = wx.BoxSizer(wx.HORIZONTAL)
        fgs = wx.FlexGridSizer(5, 2, 10, 10)
        blank = wx.Panel(panel)

        title = wx.StaticText(panel, label = "Refine Grid Settings")
        cell_size = wx.StaticText(panel, label="Cell Size")
        grid_spacing = wx.StaticText(panel, label="Grid Spacing")
        iterations = wx.StaticText(panel, label="# of Iterations")
        
        cell_sizes = [256, 512, 1024]
        cell_spacing = [128, 192, 256, 384, 512, 768]
        self.cell_size_ctrl = wx.Choice(panel, choices=list(map(str, cell_sizes)))
        self.cell_spacing_ctrl = wx.Choice(panel,  choices=list(map(str, cell_spacing)))
        self.iterations_ctrl = wx.SpinCtrl(panel, min=2, initial=5)

        self.ok_btn = wx.Button(panel, wx.ID_OK, label="OK")
        self.cancel_btn = wx.Button(panel, wx.ID_OK, label="Cancel")

        fgs.AddMany([title, blank,
                     cell_size, self.cell_size_ctrl,
                     grid_spacing, self.cell_spacing_ctrl,
                     iterations, self.iterations_ctrl,
                     self.ok_btn, (self.cancel_btn, 1, wx.EXPAND)])
        fgs.AddGrowableRow(2, 1)
        fgs.AddGrowableCol(1, 1)
        hbox.Add(fgs, proportion=2, flag=wx.ALL | wx.EXPAND, border=15)
        panel.SetSizer(hbox)

    @staticmethod
    def GetGridRefineSettings(parent: wx.Window) -> None | nornir_imageregistration.settings.GridRefinement:
        with RefineGridSettingsDialog(parent) as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                return nornir_imageregistration.settings.GridRefinement.CreateWithPreprocessedImages(
                    target_img_data=pyre.state.currentStosConfig.FixedImages,
                    source_img_data=pyre.state.currentStosConfig.WarpedImages,
                    num_iterations=dlg.iterations,
                    cell_size=dlg.cell_size,
                    grid_spacing=dlg.grid_spacing)
            else:
                return None
