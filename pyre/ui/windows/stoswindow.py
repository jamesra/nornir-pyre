import os

import wx

from nornir_imageregistration import StosFile
import nornir_imageregistration.transforms
import nornir_pools as pools
import pyre
from pyre import Space, state
import pyre.state
import pyre.ui
from pyre.ui.windows.filedrop import FileDrop
from pyre.ui.windows.textdrop import TextDrop
from pyre.ui.windows.pyrewindows import PyreWindowBase
from pyre.ui import ImageTransformViewPanel
from pyre.state import ViewType


class StosWindow(PyreWindowBase):
    stosfilename = ''
    stosdirname = ''
    imagedirname = ''
    imagepanel: ImageTransformViewPanel
    _space: Space
    dirname: str = ''
    _config: pyre.state.StosWindowConfig
    _view_type: ViewType

    @property
    def space(self) -> Space:
        """Which space images will be rendered in"""
        return self._space

    @property
    def showFixed(self) -> bool:
        return self.space == Space.Source

    @property
    def Composite(self) -> bool:
        return self.space == Space.Composite

    def lookatfixedpoint(self, point, scale):
        self.imagepanel.lookatfixedpoint(point, scale)

    @property
    def config(self) -> pyre.state.StosWindowConfig:
        return self._config

    def __init__(self, parent,
                 window_id: ViewType,
                 title: str,
                 view_type: ViewType,
                 config: pyre.state.StosWindowConfig):

        super(StosWindow, self).__init__(parent=parent, windowID=window_id, title=title,
                                         window_manager=config.window_manager)
        self._config = config
        # self.imagepanel = wx.Panel(self, -1)
        self._space = Space.Source if view_type == ViewType.Source else Space.Target if view_type == ViewType.Target else Space.Composite
        self._view_type = view_type

        self.FixedImageFullPath = None
        self.WarpedImageFullPath = None

        ###FOR DEBUGGING####
        # DataFullPath = os.path.join(os.getcwd(), "..", "Test","Data","Images")
        # FixedImageFullPath = os.path.join(DataFullPath, "0225_mosaic_64.png")
        # WarpedImageFullPath = os.path.join(DataFullPath, "0226_mosaic_64.png")
        # pyre.IrTweakInit(FixedImageFullPath, WarpedImageFullPath)
        ####################

        display_image_names = set([ViewType.Source.value, ViewType.Target.value]) if view_type == ViewType.Composite \
            else set([view_type.value])

        imagename_space_mapping = {}
        if view_type == ViewType.Composite:
            imagename_space_mapping[ViewType.Source] = Space.Source
            imagename_space_mapping[ViewType.Target] = Space.Target
        elif view_type == ViewType.Source:
            imagename_space_mapping[ViewType.Source] = Space.Source
        elif view_type == ViewType.Target:
            imagename_space_mapping[ViewType.Target] = Space.Target
        else:
            raise NotImplementedError("Unknown ViewType")

        # This is the GL Panel, so GL initialization happens after this
        image_panel_config = pyre.ui.ImageTransformPanelConfig(
            transform_controller=config.transform_controller,
            imageviewmodel_manager=config.imageviewmodel_manager,
            glcontext_manager=config.glcontext_manager,
            transformglbuffer_manager=config.transformglbuffer_manager,
            view_type=view_type,
            imagename_space_mapping=imagename_space_mapping
        )

        self.imagepanel = pyre.ui.ImageTransformViewPanel(parent=self,
                                                          space=self._space,
                                                          config=image_panel_config)

        # pyre.Config._transform_controller,
        # pyre.Config.FixedTransformView

        # self.control = wx.StaticText(panel, -1, README_Import(self), size=(800,-1))

        # Populate menu options into a File Dropdown menu.

        self.CreateMenu()

        # Allows Drag and Drop
        dt = FileDrop(self)
        self.SetDropTarget(dt)

        wx.CallAfter(self.setPosition)

        wx.CallAfter(self.Show, True)

        # Make sure we have a GL context before initializing view window
        # wx.CallAfter(self.UpdateRawImageWindow)

    def CreateMenu(self):
        menuBar = wx.MenuBar()

        filemenu = self.__CreateFileMenu()
        menuBar.Append(filemenu, "&File")

        opsmenu = self.__CreateOpsMenu()
        menuBar.Append(opsmenu, "&Operations")

        self.windmenu = self.__CreateWindowsMenu()
        menuBar.Append(self.windmenu, "&Windows")

        self.Bind(wx.EVT_CLOSE, self.OnClose)

        # self.imagepanel.SetDropTarget(FileDrop(self.imagepanel))

        # self.SetDropTarget(TextDrop(self))
        # self.DragAcceptFiles(True)

        # print "Drop target set"

        # print str(self.GetDropTarget())

        self.SetMenuBar(menuBar)

    def __CreateWindowsMenu(self):
        menu = wx.Menu()
        windowSubMenu = wx.Menu()

        displayCount = wx.Display.GetCount()

        if displayCount == 1:
            pass
        elif displayCount == 2:
            submenuWindow1 = windowSubMenu.Append(wx.ID_ANY, "Left 1 Window View")
            submenuWindow2 = windowSubMenu.Append(wx.ID_ANY, "Right 1 Window View")
            windowSubMenu.AppendSeparator()
            submenuWindow3 = windowSubMenu.Append(wx.ID_ANY, "2 Window View")

            self.Bind(wx.EVT_MENU, self.OnLeft1WindowView, submenuWindow1)
            self.Bind(wx.EVT_MENU, self.OnRight1WindowView, submenuWindow2)
            self.Bind(wx.EVT_MENU, self.On2WindowView, submenuWindow3)

            menu.Append(wx.ID_ANY, "&Window Options", windowSubMenu)

        elif displayCount >= 3:
            submenuWindow1 = windowSubMenu.Append(wx.ID_ANY, "Left 1 Window View")
            submenuWindow2 = windowSubMenu.Append(wx.ID_ANY, "Center 1 Window View")
            submenuWindow3 = windowSubMenu.Append(wx.ID_ANY, "Right 1 Window View")
            windowSubMenu.AppendSeparator()
            submenuWindow4 = windowSubMenu.Append(wx.ID_ANY, "Left 2 Window View")
            submenuWindow5 = windowSubMenu.Append(wx.ID_ANY, "Right 2 Window View")
            windowSubMenu.AppendSeparator()
            submenuWindow6 = windowSubMenu.Append(wx.ID_ANY, "3 Window View")

            self.Bind(wx.EVT_MENU, self.OnLeft1WindowView, submenuWindow1)
            self.Bind(wx.EVT_MENU, self.OnCenter1WindowView, submenuWindow2)
            self.Bind(wx.EVT_MENU, self.OnRight1WindowView, submenuWindow3)
            self.Bind(wx.EVT_MENU, self.On2WindowView, submenuWindow4)
            self.Bind(wx.EVT_MENU, self.OnRight2WindowView, submenuWindow5)
            self.Bind(wx.EVT_MENU, self.On3WindowView, submenuWindow6)

            menu.AppendMenu(wx.ID_ANY, "&Multiple display options", windowSubMenu)

        self.menuShowFixedImage = menu.Append(wx.ID_ANY, "&Fixed Image", kind=wx.ITEM_CHECK)
        menu.Check(self.menuShowFixedImage.GetId(), True)
        self.Bind(wx.EVT_MENU, self.OnShowFixedWindow, self.menuShowFixedImage)

        self.menuShowWarpedImage = menu.Append(wx.ID_ANY, "&Warped Image", kind=wx.ITEM_CHECK)
        menu.Check(self.menuShowWarpedImage.GetId(), True)
        self.Bind(wx.EVT_MENU, self.OnShowWarpedWindow, self.menuShowWarpedImage)

        self.menuShowCompositeImage = menu.Append(wx.ID_ANY, "&Composite Image", kind=wx.ITEM_CHECK)
        menu.Check(self.menuShowCompositeImage.GetId(), True)
        self.Bind(wx.EVT_MENU, self.OnShowCompositeWindow, self.menuShowCompositeImage)

        menu.AppendSeparator()

        menuRestoreOrientation = menu.Append(wx.ID_ANY, "&Restore Orientation")
        self.Bind(wx.EVT_MENU, self.OnRestoreOrientation, menuRestoreOrientation)

        return menu

    @staticmethod
    def __get_transform_type_from_menuitem(menu_item: wx.Menu) -> nornir_imageregistration.transforms.TransformType:
        if menu_item is None:
            raise ValueError('menu_item')

        return nornir_imageregistration.transforms.TransformType[menu_item.ItemLabelText]

    @staticmethod
    def __get_cell_size_from_menuitem(menu_item: wx.Menu) -> tuple[int, int]:
        if menu_item is None:
            raise ValueError('menu_item')

        option_parts = menu_item.ItemLabelText.split('x')
        option = tuple(int(d) for d in option_parts)
        return option

    def OnSetCellSize(self, e):
        from pyre.state import currentStosConfig

        menu_id = e.Id
        menu = e.EventObject
        # Find the selected child_menu since Wx passes the parent for some insane reason
        selected_item = list(filter(lambda m: m.Id == menu_id, menu.MenuItems))[0]

        cell_size = self.__get_cell_size_from_menuitem(selected_item)
        currentStosConfig.AlignmentTileSize = cell_size

        self.UpdateCellSizeChecks(menu)

    def OnSetTransformType(self, e):
        menu_id = e.Id
        menu = e.EventObject

        # Find the selected child_menu since Wx passes the parent for some insane reason
        selected_item = list(filter(lambda m: m.Id == menu_id, menu.MenuItems))[0]

        transform_type = self.__get_transform_type_from_menuitem(selected_item)

        if pyre.state.currentStosConfig.TransformType == transform_type:
            print(f"transform is already {transform_type}, no change")
            return

        converter_kwargs = self.GetTransformConfig(transform_type)
        if converter_kwargs is None:
            print("User cancelled settings, transform conversion aborted")
            return

        pyre.history.SaveState(setattr, pyre.state.currentStosConfig.TransformController, 'TransformModel',
                               pyre.state.currentStosConfig.TransformController.TransformModel)
        pyre.state.currentStosConfig.TransformController.TransformModel = \
            nornir_imageregistration.transforms.ConvertTransform(
                pyre.state.currentStosConfig.Transform, transform_type,
                source_image_shape=pyre.state.currentStosConfig.WarpedImages.Image.shape,
                **converter_kwargs)

        print(f"Changed transform type to {transform_type}")
        self.UpdateTransformTypeChecks(menu)
        return

    def OnLinearBlend(self, e):

        blend_factor_percentage = wx.GetNumberFromUser("Select a linear blend factor from 0 to 100%",
                                                       "Blend %",
                                                       "Linear Blend",
                                                       10, 0, 100,
                                                       parent=self)
        blend_factor = blend_factor_percentage / 100.0

        pyre.common.LinearBlendTransform(blend_factor=blend_factor)

    def GetTransformConfig(self, transform_type) -> dict[str, any]:
        """Returns a dictionary containing arguments to ConvertTransform
        :returns: A dictionary of parameters or None if user cancelled the dialog"""
        if transform_type == nornir_imageregistration.transforms.TransformType.GRID:
            return self.GetGridTransformConfig()

        return {}

    def GetGridTransformConfig(self) -> dict[str, any] | None:
        """Show a UI to get the transform configuration"""
        with pyre.ui.GridTransformSettingsDialog(self) as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                return {'grid_dims': dlg.grid_dims}
            else:
                return

    def UpdateCellSizeChecks(self, menu: wx.Menu):
        from pyre.state import currentStosConfig

        for m in menu.MenuItems:
            option_cell_size = self.__get_cell_size_from_menuitem(m)
            m.Check(option_cell_size == currentStosConfig.AlignmentTileSize)
            # print(m.IsChecked())

        # menu.UpdateUI()

    def UpdateTransformTypeChecks(self, menu: wx.Menu):
        from pyre.state import currentStosConfig

        current_type = self.config.transform_controller.TransformModel.type

        for m in menu.MenuItems:
            menu_item_transform_type = self.__get_transform_type_from_menuitem(m)
            m.Check(menu_item_transform_type == current_type)
            # print(f'Checked: Evaluated: {menu_item_transform_type == current_type} Control State: {m.IsChecked()}')

        # menu.UpdateUI()

    def __CreateCellSizeMenu(self):
        menu = wx.Menu()

        cell_size_options = [(128, 128),
                             (192, 192),
                             (256, 256),
                             (512, 512)]

        for option in cell_size_options:
            menu_option = menu.AppendCheckItem(wx.NewId(), f'{option[0]}x{option[1]}')
            menu_option.cell_size_option = option
            self.Bind(wx.EVT_MENU, self.OnSetCellSize, menu_option, menu_option.Id)

        return menu

    def __CreateTransformMenu(self):
        menu = wx.Menu()

        for key in nornir_imageregistration.transforms.TransformType.__members__.keys():
            menu_option = menu.AppendCheckItem(wx.NewId(), key)
            menu_option.transform_type = key
            self.Bind(wx.EVT_MENU, self.OnSetTransformType, menu_option, menu_option.Id)

        return menu

    def __CreateOpsMenu(self):
        menu = wx.Menu()

        menuRotationTranslation = menu.Append(wx.ID_ANY, "&Rotate translate estimate")
        self.Bind(wx.EVT_MENU, self.OnRotateTranslate, menuRotationTranslation)

        menuGridRefine = menu.Append(wx.ID_ANY, "&Convert to refined grid")
        self.Bind(wx.EVT_MENU, self.OnRefineGrid, menuGridRefine)

        menu.AppendSeparator()

        menuInstructions = menu.Append(wx.ID_ABOUT, "&Keyboard Instructions")
        self.Bind(wx.EVT_MENU, self.OnInstructions, menuInstructions)

        menuClearMasked = menu.Append(wx.ID_ANY, "&Clear All Masked points")
        self.Bind(wx.EVT_MENU, self.OnClearMaskedPoints, menuClearMasked)

        menuClear = menu.Append(wx.ID_ANY, "&Clear All points")
        self.Bind(wx.EVT_MENU, self.OnClearAllPoints, menuClear)

        menu.AppendSeparator()

        menu_linear_blend = menu.Append(wx.ID_ANY, "Linear Blend")
        self.Bind(wx.EVT_MENU, self.OnLinearBlend, menu_linear_blend)

        _cell_size_menu = self.__CreateCellSizeMenu()
        menu.AppendSubMenu(_cell_size_menu, "Align ROI Size", "How large of a region is used to auto-align points")
        self.UpdateCellSizeChecks(_cell_size_menu)

        menu.AppendSeparator()

        transform_menu = self.__CreateTransformMenu()
        menu.AppendSubMenu(transform_menu, "transform type", "Select the type of transform to use")
        self.UpdateTransformTypeChecks(transform_menu)

        menu.AppendSeparator()

        self.Bind(wx.EVT_MENU, self.OnClearAllPoints, menuClear)

        return menu

    def __CreateFileMenu(self):

        filemenu = wx.Menu()

        # Menu options
        menuOpenStos = filemenu.Append(wx.ID_ANY, "&Open stos file")
        self.Bind(wx.EVT_MENU, self.OnOpenStos, menuOpenStos)

        menuOpenFixedImage = filemenu.Append(wx.ID_ANY, "&Open Fixed Image")
        self.Bind(wx.EVT_MENU, self.OnOpenFixedImage, menuOpenFixedImage)

        menuOpenWarpedImage = filemenu.Append(wx.ID_ANY, "&Open Warped Image")
        self.Bind(wx.EVT_MENU, self.OnOpenWarpedImage, menuOpenWarpedImage)

        menuOpenFixedImageMask = filemenu.Append(wx.ID_ANY, "&Open Fixed Image Mask")
        self.Bind(wx.EVT_MENU, self.OnOpenFixedImageMask, menuOpenFixedImageMask)

        menuOpenWarpedImageMask = filemenu.Append(wx.ID_ANY, "&Open Warped Image Mask")
        self.Bind(wx.EVT_MENU, self.OnOpenWarpedImageMask, menuOpenWarpedImageMask)

        filemenu.AppendSeparator()

        menuSaveStos = filemenu.Append(wx.ID_ANY, "&Save Stos File")
        self.Bind(wx.EVT_MENU, self.OnSaveStos, menuSaveStos)

        menuSaveWarpedImage = filemenu.Append(wx.ID_ANY, "&Save Warped Image")
        self.Bind(wx.EVT_MENU, self.OnSaveWarpedImage, menuSaveWarpedImage)

        filemenu.AppendSeparator()

        menuExit = filemenu.Append(wx.ID_EXIT, "&Exit")
        self.Bind(wx.EVT_MENU, self.OnExit, menuExit)

        return filemenu

    #
    # def OnImageViewModelManagerChange(self, manager: pyre.state.IImageViewModelManager,
    #                                   key: str, action: pyre.state.Action, image_name: str):
    #
    #

    # def UpdateRawImageWindow(self):
    #
    #     # if hasattr(self, 'imagepanel'):
    #     #    del self.imagepanel
    #
    #     imageTransformView = None
    #     if self.Composite:
    #         imageTransformView = pyre.views.CompositeTransformView(glcontexmanager=self.config.glcontext_manager,
    #                                                                FixedImageArray=state.currentStosConfig.FixedImageViewModel,
    #                                                                WarpedImageArray=state.currentStosConfig.WarpedImageViewModel,
    #                                                                transform_controller=state.currentStosConfig.transform_controller)
    #     else:
    #         imageViewModel = state.currentStosConfig.FixedImageViewModel
    #         if not self.showFixed:
    #             imageViewModel = state.currentStosConfig.WarpedImageViewModel
    #
    #         imageTransformView = pyre.views.ImageTransformView(space=self.space,
    #                                                            glcontexmanager=self.config.glcontext_manager,
    #                                                            ImageViewModel=imageViewModel,
    #                                                            transform_controller=state.currentStosConfig.transform_controller)
    #
    #     self.imagepanel.image_transform_view = imageTransformView

    def OnShowFixedWindow(self, e):
        pyre.ToggleWindow(ViewType.Source)

    def OnShowWarpedWindow(self, e):
        pyre.ToggleWindow(ViewType.Target)

    def OnShowCompositeWindow(self, e):
        pyre.ToggleWindow(ViewType.Composite)

    def OnRestoreOrientation(self, e):
        pyre.Windows[ViewType.Composite].setPosition()
        pyre.Windows[ViewType.Target].setPosition()
        pyre.Windows[ViewType.Source].setPosition()

    def OnInstructions(self, e):

        readme = pyre.resources.README()
        dlg = wx.MessageDialog(self, readme, "Keyboard Instructions", wx.OK)
        dlg.ShowModal()
        dlg.Destroy()

    def OnClearAllPoints(self, e):
        sourceImageView = self.config.imageviewmodel_manager[ViewType.Source]
        targetImageView = self.config.imageviewmodel_manager[ViewType.Target]
        self.config.transform_controller.TransformModel = pyre.viewmodels.transformcontroller.CreateDefaultTransform(
            state.currentStosConfig.TransformType,
            sourceImageView.Image.shape,
            targetImageView.Image.shape)

    def OnClearMaskedPoints(self, e):
        if not (
                state.currentStosConfig.FixedImageMaskViewModel is None or state.currentStosConfig.WarpedImageMaskViewModel is None):
            pyre.common.ClearPointsOnMask(state.currentStosConfig.TransformController,
                                          state.currentStosConfig.FixedImageMaskViewModel.Image,
                                          state.currentStosConfig.WarpedImageMaskViewModel.Image)

        elif not state.currentStosConfig.FixedImageMaskViewModel is None:
            pyre.common.ClearPointsOnMask(state.currentStosConfig.TransformController,
                                          state.currentStosConfig.FixedImageMaskViewModel.Image, None)

        elif not state.currentStosConfig.WarpedImageMaskViewModel is None:
            pyre.common.ClearPointsOnMask(state.currentStosConfig.TransformController, None,
                                          state.currentStosConfig.WarpedImageMaskViewModel.Image)

    def OnRotateTranslate(self, e):
        pyre.common.RotateTranslateWarpedImage()

    def OnRefineGrid(self, e):
        if pyre.state.currentStosConfig.FixedImageViewModel is None or \
                pyre.state.currentStosConfig.WarpedImageViewModel is None:
            print("Need both images loaded with a transform to run refine grid")
            return None

        with pyre.ui.RefineGridSettingsDialog.GetGridRefineSettings(self) as settings:
            pyre.common.GridRefineTransform(settings)

    def OnOpenFixedImage(self, e):
        dlg = wx.FileDialog(self, "Choose a fixed image", StosWindow.imagedirname, "", "*.*", wx.FD_OPEN)
        if dlg.ShowModal() == wx.ID_OK:
            filename = str(dlg.GetFilename())
            StosWindow.imagedirname = str(dlg.GetDirectory())

            state.currentStosConfig.LoadFixedImage(os.path.join(StosWindow.imagedirname, filename))

        dlg.Destroy()
        # if Config.FixedImageFullPath is not None and Config.WarpedImageFullPath is not None:
        #    pyre.IrTweakInit(Config.FixedImageFullPath, Config.WarpedImageFullPath)

    def OnOpenWarpedImage(self, e):
        dlg = wx.FileDialog(self, "Choose an image to warp", StosWindow.imagedirname, "", "*.*", wx.FD_OPEN)
        if dlg.ShowModal() == wx.ID_OK:
            filename = str(dlg.GetFilename())
            StosWindow.imagedirname = str(dlg.GetDirectory())

            state.currentStosConfig.LoadWarpedImage(os.path.join(StosWindow.imagedirname, filename))

        dlg.Destroy()

    def OnOpenFixedImageMask(self, e):
        dlg = wx.FileDialog(self, "Choose a mask for the fixed image", StosWindow.imagedirname, "", "*.*", wx.FD_OPEN)
        if dlg.ShowModal() == wx.ID_OK:
            filename = str(dlg.GetFilename())
            StosWindow.imagedirname = str(dlg.GetDirectory())

            state.currentStosConfig.FixedImageMaskViewModel = state.currentStosConfig.LoadFixedMaskImage(
                os.path.join(StosWindow.imagedirname, filename))

        dlg.Destroy()
        # if Config.FixedImageFullPath is not None and Config.WarpedImageFullPath is not None:
        #    pyre.IrTweakInit(Config.FixedImageFullPath, Config.WarpedImageFullPath)

    def OnOpenWarpedImageMask(self, e):
        dlg = wx.FileDialog(self, "Choose a mask for the warped image", StosWindow.imagedirname, "", "*.*", wx.FD_OPEN)
        if dlg.ShowModal() == wx.ID_OK:
            filename = str(dlg.GetFilename())
            StosWindow.imagedirname = str(dlg.GetDirectory())

            state.currentStosConfig.WarpedImageMaskViewModel = state.currentStosConfig.LoadWarpedMaskImage(
                os.path.join(StosWindow.imagedirname, filename))

        dlg.Destroy()

        # if Config.FixedImageFullPath is not None and Config.WarpedImageFullPath is not None:
        #    pyre.IrTweakInit(Config.FixedImageFullPath, Config.WarpedImageFullPath)

    def OnOpenStos(self, e):
        dirname = pyre.state.currentStosConfig.stosdirname
        dlg = wx.FileDialog(self, "Choose a file", dirname, "", "*.stos", wx.FD_OPEN)
        if dlg.ShowModal() == wx.ID_OK:
            filename = str(dlg.GetFilename())
            self.dirname = str(dlg.GetDirectory())
            StosWindow.stosfilename = filename

            state.currentStosConfig.LoadStos(os.path.join(self.dirname,
                                                          filename))

        dlg.Destroy()

    def OnSaveWarpedImage(self, e):
        # Set the path for the output directory.
        if not (
                pyre.state.currentStosConfig.FixedImageViewModel is None or pyre.state.currentStosConfig.WarpedImageViewModel is None):
            dlg = wx.FileDialog(self, "Choose a Directory", StosWindow.imagedirname, "", "*.png", wx.FD_SAVE)
            if dlg.ShowModal() == wx.ID_OK:
                StosWindow.imagedirname = dlg.GetDirectory()
                self.filename = dlg.GetFilename()
                state.currentStosConfig.OutputImageFullPath = os.path.join(StosWindow.imagedirname, self.filename)

                #                 common.SaveRegisteredWarpedImage(pyre.state.currentStosConfig.OutputImageFullPath,
                #                                                  pyre.state.currentStosConfig.transform,
                #                                                  pyre.state.currentStosConfig.WarpedImageViewModel.Image)
                pool = pools.GetGlobalThreadPool()
                pool.add_task("Save " + pyre.state.currentStosConfig.OutputImageFullPath,
                              common.SaveRegisteredWarpedImage,
                              state.currentStosConfig.OutputImageFullPath,
                              state.currentStosConfig.Transform,
                              state.currentStosConfig.WarpedImageViewModel.Image)

    def OnSaveStos(self, e):
        if not (state.currentStosConfig.TransformController is None):
            dlg = wx.FileDialog(self, "Choose a Directory",
                                state.currentStosConfig.stosdirname,
                                state.currentStosConfig.stosfilename, "*.stos",
                                wx.FD_SAVE)
            if dlg.ShowModal() == wx.ID_OK:
                state.currentStosConfig.stosdirname = dlg.GetDirectory()
                state.currentStosConfig.stosfilename = dlg.GetFilename()
                saveFileFullPath = os.path.join(StosWindow.stosdirname, StosWindow.stosfilename)

                stosObj = StosFile.Create(state.currentStosConfig.FixedImageFullPath,
                                          state.currentStosConfig.WarpedImageFullPath,
                                          state.currentStosConfig.Transform,
                                          state.currentStosConfig.FixedImageMaskFullPath,
                                          state.currentStosConfig.WarpedImageMaskFullPath)
                stosObj.Save(saveFileFullPath)
            dlg.Destroy()
