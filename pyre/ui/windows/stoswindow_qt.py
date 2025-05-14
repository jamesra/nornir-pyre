import os

from dependency_injector.wiring import Provide, inject
from PyQt6.QtWidgets import QMenu, QMenuBar, QFileDialog, QMessageBox, QInputDialog
from PyQt6.QtCore import Qt, QEvent

from nornir_shared import prettyoutput
import nornir_imageregistration
from nornir_imageregistration import StosFile
from nornir_imageregistration.settings import GridRefinement
import nornir_imageregistration.transforms
import nornir_pools as pools
import pyre
from pyre.settings import AppSettings, StosSettings, ImageAndMaskPath
from pyre.space import Space
from pyre.container import IContainer
from pyre.interfaces.managers import ICommandHistory, IImageManager, IImageViewModelManager, IImageLoader
import pyre.state
from pyre.interfaces.viewtype import ViewType
from pyre.interfaces.named_tuples import LoadStosResult
import pyre.ui
from pyre.ui.widgets import ImageTransformViewPanel
from pyre.ui.windows.filedrop_qt import FileDrop
from pyre.ui.windows.pyrewindows_qt import PyreWindowBase
from pyre.stos_container import StosContainer
from pyre.observable import ObservableSet


class StosWindow(PyreWindowBase):
    stosfilename = ''
    stosdirname = ''
    imagedirname = ''
    imagepanel: ImageTransformViewPanel
    _space: Space
    dirname: str = ''
    _view_type: ViewType
    _selected_points: ObservableSet[int] = Provide[StosContainer.selected_points]
    _transform_controller: pyre.state.TransformController
    _imageviewmodel_manager: IImageViewModelManager = Provide[IContainer.imageviewmodel_manager]
    _history_manager: ICommandHistory = Provide[IContainer.history_manager]
    _config = Provide[IContainer.config]
    _settings: AppSettings = Provide[IContainer.settings]
    _image_manager: IImageManager = Provide[IContainer.image_manager]

    @property
    def transform_controller(self) -> pyre.state.TransformController:
        return self._transform_controller

    @property
    def space(self) -> Space:
        """Which space images will be rendered in"""
        return self._space

    @property
    def showFixed(self) -> bool:
        return self.space == Space.Source

    @property
    def Composite(self) -> bool:
        return self._view_type == ViewType.Composite

    def lookatfixedpoint(self, point, scale):
        self.imagepanel.lookatfixedpoint(point, scale)

    @inject
    def __init__(self, parent,
                 window_id: ViewType,
                 title: str,
                 view_type: ViewType,
                 transform_controller: pyre.state.TransformController = Provide[IContainer.transform_controller]):

        super(StosWindow, self).__init__(parent=parent, windowID=window_id, title=title)

        self._transform_controller = transform_controller
        self._space = Space.Source if view_type == ViewType.Source else Space.Target
        self._view_type = view_type

        self.FixedImageFullPath = None
        self.WarpedImageFullPath = None

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

        self.imagepanel = ImageTransformViewPanel(parent=self,
                                                 space=self._space,
                                                 view_type=view_type,
                                                 transform_controller=transform_controller,
                                                 imagename_space_mapping=imagename_space_mapping,
                                                 selected_points=self._selected_points)

        # Set the image panel as the central widget
        self.setCentralWidget(self.imagepanel)

        # Create menu
        self.createMenu()

        # Allows Drag and Drop
        dt = FileDrop(self)
        self.setAcceptDrops(True)

        # Show the window and set position
        self.setPosition()
        self.show()

    def createMenu(self):
        """Create the menu bar and menus"""
        menuBar = QMenuBar(self)
        self.setMenuBar(menuBar)

        # Create File menu
        filemenu = self.__createFileMenu()
        menuBar.addMenu(filemenu)

        # Create Operations menu
        opsmenu = self.__createOpsMenu()
        menuBar.addMenu(opsmenu)

        # Create Windows menu
        self.windmenu = self.__createWindowsMenu()
        menuBar.addMenu(self.windmenu)

    def __createWindowsMenu(self):
        """Create the Windows menu"""
        from PyQt6.QtGui import QGuiApplication
        
        menu = QMenu("&Windows", self)
        windowSubMenu = QMenu("Window Options", self)

        displayCount = len(QGuiApplication.screens())

        if displayCount == 1:
            pass
        elif displayCount == 2:
            submenuWindow1 = windowSubMenu.addAction("Left 1 Window View")
            submenuWindow2 = windowSubMenu.addAction("Right 1 Window View")
            windowSubMenu.addSeparator()
            submenuWindow3 = windowSubMenu.addAction("2 Window View")

            submenuWindow1.triggered.connect(self.onLeft1WindowView)
            submenuWindow2.triggered.connect(self.onRight1WindowView)
            submenuWindow3.triggered.connect(self.on2WindowView)

            menu.addMenu(windowSubMenu)

        elif displayCount >= 3:
            submenuWindow1 = windowSubMenu.addAction("Left 1 Window View")
            submenuWindow2 = windowSubMenu.addAction("Center 1 Window View")
            submenuWindow3 = windowSubMenu.addAction("Right 1 Window View")
            windowSubMenu.addSeparator()
            submenuWindow4 = windowSubMenu.addAction("Left 2 Window View")
            submenuWindow5 = windowSubMenu.addAction("Right 2 Window View")
            windowSubMenu.addSeparator()
            submenuWindow6 = windowSubMenu.addAction("3 Window View")

            submenuWindow1.triggered.connect(self.onLeft1WindowView)
            submenuWindow2.triggered.connect(self.onCenter1WindowView)
            submenuWindow3.triggered.connect(self.onRight1WindowView)
            submenuWindow4.triggered.connect(self.on2WindowView)
            submenuWindow5.triggered.connect(self.onRight2WindowView)
            submenuWindow6.triggered.connect(self.on3WindowView)

            menu.addMenu(windowSubMenu)

        # Add checkable menu items for showing/hiding windows
        self.menuShowFixedImage = menu.addAction("&Target Image")
        self.menuShowFixedImage.setCheckable(True)
        self.menuShowFixedImage.setChecked(True)
        self.menuShowFixedImage.triggered.connect(self.onShowTargetWindow)

        self.menuShowWarpedImage = menu.addAction("&Source Image")
        self.menuShowWarpedImage.setCheckable(True)
        self.menuShowWarpedImage.setChecked(True)
        self.menuShowWarpedImage.triggered.connect(self.onShowSourceWindow)

        self.menuShowCompositeImage = menu.addAction("&Composite Image")
        self.menuShowCompositeImage.setCheckable(True)
        self.menuShowCompositeImage.setChecked(True)
        self.menuShowCompositeImage.triggered.connect(self.onShowCompositeWindow)

        menu.addSeparator()

        menuRestoreOrientation = menu.addAction("&Restore Orientation")
        menuRestoreOrientation.triggered.connect(self.onRestoreOrientation)

        return menu

    @staticmethod
    def __get_transform_type_from_menuitem(action) -> nornir_imageregistration.transforms.TransformType:
        if action is None:
            raise ValueError('action')

        return nornir_imageregistration.transforms.TransformType[action.text()]

    @staticmethod
    def __get_cell_size_from_menuitem(action) -> tuple[int, int]:
        if action is None:
            raise ValueError('action')

        option_parts = action.text().split('x')
        option = tuple(int(d) for d in option_parts)
        return option

    def onSetCellSize(self, checked):
        from pyre.state import currentStosConfig

        action = self.sender()
        cell_size = self.__get_cell_size_from_menuitem(action)
        currentStosConfig.AlignmentTileSize = cell_size

        self.updateCellSizeChecks(action.parentWidget())

    def onSetTransformType(self, checked):
        action = self.sender()
        transform_type = self.__get_transform_type_from_menuitem(action)

        if pyre.state.currentStosConfig.TransformType == transform_type:
            print(f"transform is already {transform_type}, no change")
            return

        converter_kwargs = self.getTransformConfig(transform_type)
        if converter_kwargs is None:
            print("User cancelled settings, transform conversion aborted")
            return

        source_imageviewmodel = self._imageviewmodel_manager[ViewType.Source]
        self.transform_controller.TransformModel = \
            nornir_imageregistration.transforms.ConvertTransform(
                self.transform_controller.TransformModel, transform_type,
                source_image_shape=source_imageviewmodel.Image.shape,
                **converter_kwargs)

        print(f"Changed transform type to {transform_type}")
        self.updateTransformTypeChecks(action.parentWidget())
        return

    def onLinearBlend(self):
        blend_factor_percentage, ok = QInputDialog.getInt(
            self, 
            "Linear Blend", 
            "Select a linear blend factor from 0 to 100%", 
            10, 0, 100, 1
        )
        
        if ok:
            blend_factor = blend_factor_percentage / 100.0
            pyre.common.LinearBlendTransform(blend_factor=blend_factor)

    def getTransformConfig(self, transform_type) -> dict[str, any]:
        """Returns a dictionary containing arguments to ConvertTransform
        :returns: A dictionary of parameters or None if user cancelled the dialog"""
        if transform_type == nornir_imageregistration.transforms.TransformType.GRID:
            return self.getGridTransformConfig()

        return {}

    def getGridTransformConfig(self) -> dict[str, any] | None:
        """Show a UI to get the transform configuration"""
        with pyre.ui.windows.GridTransformSettingsDialog(self) as dlg:
            if dlg.exec() == QFileDialog.DialogCode.Accepted:
                return {'grid_dims': dlg.grid_dims}
            else:
                return None

    def updateCellSizeChecks(self, menu):
        from pyre.state import currentStosConfig

        for action in menu.actions():
            try:
                option_cell_size = self.__get_cell_size_from_menuitem(action)
                action.setChecked(option_cell_size == currentStosConfig.AlignmentTileSize)
            except:
                # Skip actions that don't have cell size format
                pass

    def updateTransformTypeChecks(self, menu):
        current_type = self.transform_controller.TransformModel.type

        for action in menu.actions():
            try:
                menu_item_transform_type = self.__get_transform_type_from_menuitem(action)
                action.setChecked(menu_item_transform_type == current_type)
            except:
                # Skip actions that don't have transform type format
                pass

    def __createCellSizeMenu(self):
        menu = QMenu("Cell Size", self)

        cell_size_options = [(128, 128),
                           (192, 192),
                           (256, 256),
                           (512, 512)]

        for option in cell_size_options:
            menu_option = menu.addAction(f'{option[0]}x{option[1]}')
            menu_option.setCheckable(True)
            menu_option.triggered.connect(self.onSetCellSize)

        return menu

    def __createTransformMenu(self):
        menu = QMenu("Transform Type", self)

        for key in nornir_imageregistration.transforms.TransformType.__members__.keys():
            menu_option = menu.addAction(key)
            menu_option.setCheckable(True)
            menu_option.triggered.connect(self.onSetTransformType)

        return menu

    def __createOpsMenu(self):
        menu = QMenu("&Operations", self)

        menuFlip = menu.addAction("&Flip Image")
        menuFlip.triggered.connect(self.onFlipImage)

        menuRotationTranslation = menu.addAction("&Rotate translate estimate")
        menuRotationTranslation.triggered.connect(self.onRotateTranslate)

        menuGridRefine = menu.addAction("&Convert to refined grid")
        menuGridRefine.triggered.connect(self.onRefineGrid)

        menu.addSeparator()

        menuInstructions = menu.addAction("&Keyboard Instructions")
        menuInstructions.triggered.connect(self.onInstructions)

        menuClearMasked = menu.addAction("&Clear All Masked points")
        menuClearMasked.triggered.connect(self.onClearMaskedPoints)

        menuClear = menu.addAction("&Clear All points")
        menuClear.triggered.connect(self.onClearAllPoints)

        menu.addSeparator()

        menu_linear_blend = menu.addAction("Linear Blend")
        menu_linear_blend.triggered.connect(self.onLinearBlend)

        _cell_size_menu = self.__createCellSizeMenu()
        menu.addMenu(_cell_size_menu)
        self.updateCellSizeChecks(_cell_size_menu)

        menu.addSeparator()

        transform_menu = self.__createTransformMenu()
        menu.addMenu(transform_menu)
        self.updateTransformTypeChecks(transform_menu)

        return menu

    def __createFileMenu(self):
        filemenu = QMenu("&File", self)

        # Menu options
        menuOpenStos = filemenu.addAction("&Open stos file")
        menuOpenStos.triggered.connect(self.onOpenStos)

        menuOpenFixedImage = filemenu.addAction("&Open Fixed Image")
        menuOpenFixedImage.triggered.connect(self.onOpenFixedImage)

        menuOpenWarpedImage = filemenu.addAction("&Open Warped Image")
        menuOpenWarpedImage.triggered.connect(self.onOpenWarpedImage)

        menuOpenFixedImageMask = filemenu.addAction("&Open Fixed Image Mask")
        menuOpenFixedImageMask.triggered.connect(self.onOpenFixedImageMask)

        menuOpenWarpedImageMask = filemenu.addAction("&Open Warped Image Mask")
        menuOpenWarpedImageMask.triggered.connect(self.onOpenWarpedImageMask)

        filemenu.addSeparator()

        menuSaveStos = filemenu.addAction("&Save Stos File")
        menuSaveStos.triggered.connect(self.onSaveStos)

        menuSaveWarpedImage = filemenu.addAction("&Save Warped Image")
        menuSaveWarpedImage.triggered.connect(self.onSaveWarpedImage)

        filemenu.addSeparator()

        menuExit = filemenu.addAction("&Exit")
        menuExit.triggered.connect(self.onExit)

        return filemenu

    def onShowTargetWindow(self):
        window = self._window_manager[ViewType.Target.value]
        window.setVisible(not window.isVisible())

    def onShowSourceWindow(self):
        window = self._window_manager[ViewType.Source.value]
        window.setVisible(not window.isVisible())

    def onShowCompositeWindow(self):
        window = self._window_manager[ViewType.Composite.value]
        window.setVisible(not window.isVisible())

    def onRestoreOrientation(self):
        self._window_manager[ViewType.Composite.value].setPosition()
        self._window_manager[ViewType.Target.value].setPosition()
        self._window_manager[ViewType.Source.value].setPosition()

    def onInstructions(self):
        dlg = QMessageBox(self)
        dlg.setWindowTitle("Keyboard Instructions")
        dlg.setText(self._config["readme"])
        dlg.setStandardButtons(QMessageBox.StandardButton.Ok)
        dlg.exec()

    def onClearAllPoints(self):
        sourceImageView = self._imageviewmodel_manager[ViewType.Source]
        targetImageView = self._imageviewmodel_manager[ViewType.Target]
        self.transform_controller.TransformModel = pyre.controllers.transformcontroller.CreateDefaultTransform(
            pyre.state.currentStosConfig.TransformType,
            sourceImageView.Image.shape,
            targetImageView.Image.shape)

    def onClearMaskedPoints(self):
        if not (
                pyre.state.currentStosConfig.FixedImageMaskViewModel is None or pyre.state.currentStosConfig.WarpedImageMaskViewModel is None):
            pyre.common.ClearPointsOnMask(self._transform_controller.TransformModel,
                                         pyre.state.currentStosConfig.FixedImageMaskViewModel.Image,
                                         pyre.state.currentStosConfig.WarpedImageMaskViewModel.Image)

        elif not pyre.state.currentStosConfig.FixedImageMaskViewModel is None:
            pyre.common.ClearPointsOnMask(self._transform_controller.TransformModel,
                                         pyre.state.currentStosConfig.FixedImageMaskViewModel.Image, None)

        elif not pyre.state.currentStosConfig.WarpedImageMaskViewModel is None:
            pyre.common.ClearPointsOnMask(self._transform_controller.TransformModel, None,
                                         pyre.state.currentStosConfig.WarpedImageMaskViewModel.Image)

    def onFlipImage(self):
        self.transform_controller.FlipWarped()

    def onRotateTranslate(self):
        settings = self._settings.stos.brute_registration
        resulting_transform = pyre.common.RotateTranslateWarpedImage(source_image_key=Space.Source,
                                                                   target_image_key=Space.Target,
                                                                   settings=settings,
                                                                   LimitImageSize=True
                                                                   )

        if resulting_transform is not None:
            self._transform_controller.TransformModel = resulting_transform

    def onRefineGrid(self):
        if self._settings.stos.source_image is None or \
                self._settings.stos.target_image is None:
            print("Need both images loaded with a transform to run refine grid")
            return None

        user_settings = pyre.ui.windows.RefineGridSettingsDialog.GetGridRefineSettings(self)
        if user_settings is not None:
            with nornir_imageregistration.settings.GridRefinement.CreateWithPreprocessedImages(
                    source_img_data=self._image_manager[ViewType.Source],
                    target_img_data=self._image_manager[ViewType.Target],
                    num_iterations=user_settings.num_iterations,
                    grid_spacing=user_settings.grid_spacing,
                    cell_size=user_settings.cell_size,
                    angles_to_search=user_settings.angle_range) as grid_refinement_settings:
                pyre.common.GridRefineTransform(grid_refinement_settings)

    def onOpenFixedImage(self):
        dialog = QFileDialog(self)
        dialog.setWindowTitle("Choose a fixed image")
        dialog.setDirectory(StosWindow.imagedirname)
        dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        
        if dialog.exec() == QFileDialog.DialogCode.Accepted:
            selected_files = dialog.selectedFiles()
            if selected_files:
                filepath = selected_files[0]
                filename = os.path.basename(filepath)
                StosWindow.imagedirname = os.path.dirname(filepath)

                pyre.state.currentStosConfig.LoadFixedImage(filepath)

    def onOpenWarpedImage(self):
        dialog = QFileDialog(self)
        dialog.setWindowTitle("Choose an image to warp")
        dialog.setDirectory(StosWindow.imagedirname)
        dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        
        if dialog.exec() == QFileDialog.DialogCode.Accepted:
            selected_files = dialog.selectedFiles()
            if selected_files:
                filepath = selected_files[0]
                filename = os.path.basename(filepath)
                StosWindow.imagedirname = os.path.dirname(filepath)

                pyre.state.currentStosConfig.LoadWarpedImage(filepath)

    def onOpenFixedImageMask(self):
        dialog = QFileDialog(self)
        dialog.setWindowTitle("Choose a mask for the fixed image")
        dialog.setDirectory(StosWindow.imagedirname)
        dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        
        if dialog.exec() == QFileDialog.DialogCode.Accepted:
            selected_files = dialog.selectedFiles()
            if selected_files:
                filepath = selected_files[0]
                filename = os.path.basename(filepath)
                StosWindow.imagedirname = os.path.dirname(filepath)

                pyre.state.currentStosConfig.FixedImageMaskViewModel = state.currentStosConfig.LoadFixedMaskImage(filepath)

    def onOpenWarpedImageMask(self):
        dialog = QFileDialog(self)
        dialog.setWindowTitle("Choose a mask for the warped image")
        dialog.setDirectory(StosWindow.imagedirname)
        dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        
        if dialog.exec() == QFileDialog.DialogCode.Accepted:
            selected_files = dialog.selectedFiles()
            if selected_files:
                filepath = selected_files[0]
                filename = os.path.basename(filepath)
                StosWindow.imagedirname = os.path.dirname(filepath)

                pyre.state.currentStosConfig.WarpedImageMaskViewModel = state.currentStosConfig.LoadWarpedMaskImage(filepath)

    def onOpenStos(self):
        dirname = pyre.state.currentStosConfig.stosdirname
        dialog = QFileDialog(self)
        dialog.setWindowTitle("Choose a file")
        dialog.setDirectory(dirname)
        dialog.setNameFilter("Stos files (*.stos)")
        dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        
        if dialog.exec() == QFileDialog.DialogCode.Accepted:
            selected_files = dialog.selectedFiles()
            if selected_files:
                filepath = selected_files[0]
                filename = os.path.basename(filepath)
                self.dirname = os.path.dirname(filepath)
                StosWindow.stosfilename = filename

                self.loadStos(filepath)

    @staticmethod
    def loadStos(filename: str,
               image_loader: IImageLoader = Provide[IContainer.image_loader],
               stos_transform_controller: pyre.state.TransformController = Provide[
                   StosContainer.transform_controller],
               settings: pyre.settings.AppSettings = Provide[IContainer.settings]) -> LoadStosResult | None:
        try:
            load_result = image_loader.load_stos(filename)
            settings.stos.stos_filename = filename
            transform = nornir_imageregistration.transforms.LoadTransform(load_result.stos.Transform)
            stos_transform_controller.TransformModel = transform

            settings.stos.source_image = ImageAndMaskPath(image_fullpath=load_result.source.image_fullpath,
                                                        mask_fullpath=load_result.source.mask_fullpath)
            settings.stos.target_image = ImageAndMaskPath(image_fullpath=load_result.target.image_fullpath,
                                                        mask_fullpath=load_result.target.mask_fullpath)

            return load_result

        except Exception as e:
            print(f"Error loading stos file: {e}")
            return None

    def onSaveWarpedImage(self):
        # Set the path for the output directory.
        if not (
                pyre.state.currentStosConfig.FixedImageViewModel is None or pyre.state.currentStosConfig.WarpedImageViewModel is None):
            dialog = QFileDialog(self)
            dialog.setWindowTitle("Choose a Directory")
            dialog.setDirectory(StosWindow.imagedirname)
            dialog.setNameFilter("PNG files (*.png)")
            dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
            
            if dialog.exec() == QFileDialog.DialogCode.Accepted:
                selected_files = dialog.selectedFiles()
                if selected_files:
                    filepath = selected_files[0]
                    StosWindow.imagedirname = os.path.dirname(filepath)
                    self.filename = os.path.basename(filepath)
                    pyre.state.currentStosConfig.OutputImageFullPath = filepath

                    pool = pools.GetGlobalThreadPool()
                    pool.add_task("Save " + pyre.state.currentStosConfig.OutputImageFullPath,
                                 pyre.common.SaveRegisteredWarpedImage,
                                 pyre.state.currentStosConfig.OutputImageFullPath,
                                 pyre.state.currentStosConfig.Transform,
                                 pyre.state.currentStosConfig.WarpedImageViewModel.Image)

    def onSaveStos(self):
        if not (self._transform_controller is None):
            if self._settings.stos.stos_filename is not None:
                dirname = os.path.dirname(self._settings.stos.stos_filename)
                filename = os.path.basename(self._settings.stos.stos_filename)
            else:
                dirname = os.getcwd()
                filename = None

            dialog = QFileDialog(self)
            dialog.setWindowTitle("Choose a Directory")
            dialog.setDirectory(dirname)
            dialog.setNameFilter("Stos files (*.stos)")
            dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
            if filename:
                dialog.selectFile(filename)
            
            if dialog.exec() == QFileDialog.DialogCode.Accepted:
                try:
                    selected_files = dialog.selectedFiles()
                    if selected_files:
                        fullpath = selected_files[0]
                        self._settings.stos.stos_filename = fullpath

                        stosObj = StosFile.Create(
                            self._settings.stos.target_image.image_fullpath,
                            self._settings.stos.source_image.image_fullpath,
                            self._transform_controller.TransformModel,
                            self._settings.stos.target_image.mask_fullpath,
                            self._settings.stos.source_image.mask_fullpath, )
                        stosObj.Save(fullpath)
                except ValueError:
                    prettyoutput.LogErr(f"Error saving stos file {fullpath}")