import wx

class GridTransformSettingsDialog(wx.Dialog):

    @property
    def columns(self):
        return self.width_ctrl.GetValue()

    @property
    def rows(self):
        return self.height_ctrl.GetValue()

    @property
    def grid_dims(self):
        return self.rows, self.columns

    def __init__(self, parent, **kwargs):
        super(GridTransformSettingsDialog, self).__init__(parent, **kwargs)
        panel = wx.Panel(self)
        hbox = wx.BoxSizer(wx.HORIZONTAL)
        fgs = wx.FlexGridSizer(4, 2, 10, 10)
        blank = wx.Panel(panel)

        title = wx.StaticText(panel, label = "Grid Transform Settings")
        width = wx.StaticText(panel, label="Columns")
        height = wx.StaticText(panel, label="Rows")

        self.width_ctrl = wx.SpinCtrl(panel, min=2, initial=8)
        self.height_ctrl = wx.SpinCtrl(panel, min=2, initial=8)

        self.ok_btn = wx.Button(panel, wx.ID_OK, label="OK")
        self.cancel_btn = wx.Button(panel, wx.ID_OK, label="Cancel")

        fgs.AddMany([title, blank,
                     width, self.width_ctrl,
                     height, self.height_ctrl,
                     self.ok_btn, (self.cancel_btn, 1, wx.EXPAND)])
        fgs.AddGrowableRow(2, 1)
        fgs.AddGrowableCol(1, 1)
        hbox.Add(fgs, proportion=2, flag=wx.ALL | wx.EXPAND, border=15)
        panel.SetSizer(hbox)

