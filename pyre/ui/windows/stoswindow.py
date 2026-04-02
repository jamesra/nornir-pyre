import os
import logging

from dependency_injector.wiring import Provide, inject
from PyQt6.QtWidgets import QFileDialog, QMessageBox, QMenu, QMenuBar
from PyQt6.QtCore import Qt

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
from pyre.ui.windows.filedrop import FileDrop
from pyre.ui.windows.pyrewindows import PyreWindowBase
from pyre.stos_container import StosContainer
from pyre.observable import ObservableSet

logger = logging.getLogger(__name__)


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
            imagename_space_mapping[ViewType.Source.value] = Space.Source
            imagename_space_mapping[ViewType.Target.value] = Space.Target
        elif view_type == ViewType.Source:
            imagename_space_mapping[ViewType.Source.value] = Space.Source
        elif view_type == ViewType.Target:
            imagename_space_mapping[ViewType.Target.value] = Space.Target
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

        # Add drag and drop support
        self.file_drop = FileDrop(self)

        # Show the window and set position
        self.show()
        self.setPosition()

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
        menu = QMenu("&Windows", self)

        from PyQt6.QtGui import QGuiApplication
        displayCount = len(QGuiApplication.screens())

        if displayCount == 1:
            pass
        elif displayCount == 2:
            submenuWindow1 = menu.addAction("Left 1 Window View")
            submenuWindow2 = menu.addAction("Right 1 Window View")
            menu.addSeparator()
            submenuWindow3 = menu.addAction("2 Window View")

            submenuWindow1.triggered.connect(self.onLeft1WindowView)  # type: ignore[union-attr]
            submenuWindow2.triggered.connect(self.onRight1WindowView)  # type: ignore[union-attr]
            submenuWindow3.triggered.connect(self.on2WindowView)  # type: ignore[union-attr]

        elif displayCount >= 3:
            submenuWindow1 = menu.addAction("Left 1 Window View")
            submenuWindow2 = menu.addAction("Center 1 Window View")
            submenuWindow3 = menu.addAction("Right 1 Window View")
            menu.addSeparator()
            submenuWindow4 = menu.addAction("Left 2 Window View")
            submenuWindow5 = menu.addAction("Right 2 Window View")
            menu.addSeparator()
            submenuWindow6 = menu.addAction("3 Window View")

            submenuWindow1.triggered.connect(self.onLeft1WindowView)  # type: ignore[union-attr]
            submenuWindow2.triggered.connect(self.onCenter1WindowView)  # type: ignore[union-attr]
            submenuWindow3.triggered.connect(self.onRight1WindowView)  # type: ignore[union-attr]
            submenuWindow4.triggered.connect(self.on2WindowView)  # type: ignore[union-attr]
            submenuWindow5.triggered.connect(self.onRight2WindowView)  # type: ignore[union-attr]
            submenuWindow6.triggered.connect(self.on3WindowView)  # type: ignore[union-attr]

        # Add checkable menu items for showing different windows
        self.menuShowFixedImage = menu.addAction("&Target Image")
        self.menuShowFixedImage.setCheckable(True)  # type: ignore[union-attr]
        self.menuShowFixedImage.setChecked(True)  # type: ignore[union-attr]
        self.menuShowFixedImage.triggered.connect(self.onShowTargetWindow)  # type: ignore[union-attr]

        self.menuShowWarpedImage = menu.addAction("&Source Image")
        self.menuShowWarpedImage.setCheckable(True)  # type: ignore[union-attr]
        self.menuShowWarpedImage.setChecked(True)  # type: ignore[union-attr]
        self.menuShowWarpedImage.triggered.connect(self.onShowSourceWindow)  # type: ignore[union-attr]

        self.menuShowCompositeImage = menu.addAction("&Composite Image")
        self.menuShowCompositeImage.setCheckable(True)  # type: ignore[union-attr]
        self.menuShowCompositeImage.setChecked(True)  # type: ignore[union-attr]
        self.menuShowCompositeImage.triggered.connect(self.onShowCompositeWindow)  # type: ignore[union-attr]

        menu.addSeparator()

        menuRestoreOrientation = menu.addAction("&Restore Orientation")
        menuRestoreOrientation.triggered.connect(self.onRestoreOrientation)  # type: ignore[union-attr]

        return menu

    def __createOpsMenu(self):
        """Create the Operations menu"""
        menu = QMenu("&Operations", self)

        menuFlip = menu.addAction("&Flip Image")
        menuFlip.triggered.connect(self.onFlipImage)  # type: ignore[union-attr]

        convertSubmenu = menu.addMenu("Convert Transform &Type")
        assert convertSubmenu is not None
        convertToRigid = convertSubmenu.addAction("&Rigid")
        convertToRigid.triggered.connect(self.onConvertToRigid)  # type: ignore[union-attr]
        convertToGrid = convertSubmenu.addAction("&Grid")
        convertToGrid.triggered.connect(self.onConvertToGrid)  # type: ignore[union-attr]
        convertToMesh = convertSubmenu.addAction("&Mesh")
        convertToMesh.triggered.connect(self.onConvertToMesh)  # type: ignore[union-attr]
        convertToRbf = convertSubmenu.addAction("&RBF")
        convertToRbf.triggered.connect(self.onConvertToRbf)  # type: ignore[union-attr]

        menu.addSeparator()

        menuRotationTranslation = menu.addAction("&Rotate translate estimate")
        menuRotationTranslation.triggered.connect(self.onRotateTranslate)  # type: ignore[union-attr]

        menuGridRefine = menu.addAction("&Convert to refined grid")
        menuGridRefine.triggered.connect(self.onRefineGrid)  # type: ignore[union-attr]

        menu.addSeparator()

        menuInstructions = menu.addAction("&Keyboard Instructions")
        menuInstructions.triggered.connect(self.onInstructions)  # type: ignore[union-attr]

        menuClearMasked = menu.addAction("&Clear All Masked points")
        menuClearMasked.triggered.connect(self.onClearMaskedPoints)  # type: ignore[union-attr]

        menuClear = menu.addAction("&Clear All points")
        menuClear.triggered.connect(self.onClearAllPoints)  # type: ignore[union-attr]

        return menu

    def __createFileMenu(self):
        """Create the File menu"""
        filemenu = QMenu("&File", self)

        # Open stos action
        menuOpenStos = filemenu.addAction("&Open stos file")
        menuOpenStos.triggered.connect(self.onOpenStos)  # type: ignore[union-attr]

        # Open fixed image action
        menuOpenFixedImage = filemenu.addAction("&Open Fixed Image")
        menuOpenFixedImage.triggered.connect(self.onOpenFixedImage)  # type: ignore[union-attr]

        # Open warped image action
        menuOpenWarpedImage = filemenu.addAction("&Open Warped Image")
        menuOpenWarpedImage.triggered.connect(self.onOpenWarpedImage)  # type: ignore[union-attr]

        # Open fixed image mask action
        menuOpenFixedImageMask = filemenu.addAction("&Open Fixed Image Mask")
        menuOpenFixedImageMask.triggered.connect(self.onOpenFixedImageMask)  # type: ignore[union-attr]

        # Open warped image mask action
        menuOpenWarpedImageMask = filemenu.addAction("&Open Warped Image Mask")
        menuOpenWarpedImageMask.triggered.connect(self.onOpenWarpedImageMask)  # type: ignore[union-attr]

        filemenu.addSeparator()

        # Save stos action
        menuSaveStos = filemenu.addAction("&Save Stos File")
        menuSaveStos.triggered.connect(self.onSaveStos)  # type: ignore[union-attr]

        # Save warped image action
        menuSaveWarpedImage = filemenu.addAction("&Save Warped Image")
        menuSaveWarpedImage.triggered.connect(self.onSaveWarpedImage)  # type: ignore[union-attr]

        filemenu.addSeparator()

        # Exit action
        menuExit = filemenu.addAction("&Exit")
        menuExit.triggered.connect(self.onExit)  # type: ignore[union-attr]

        return filemenu

    def onShowTargetWindow(self):
        """Handle Show Target Window action"""
        window = self._window_manager[ViewType.Target.value]
        window.setVisible(not window.isVisible())

    def onShowSourceWindow(self):
        """Handle Show Source Window action"""
        window = self._window_manager[ViewType.Source.value]
        window.setVisible(not window.isVisible())

    def onShowCompositeWindow(self):
        """Handle Show Composite Window action"""
        window = self._window_manager[ViewType.Composite.value]
        window.setVisible(not window.isVisible())

    def onRestoreOrientation(self):
        """Handle Restore Orientation action"""
        self._window_manager[ViewType.Composite.value].setPosition()  # type: ignore[attr-defined]
        self._window_manager[ViewType.Target.value].setPosition()  # type: ignore[attr-defined]
        self._window_manager[ViewType.Source.value].setPosition()  # type: ignore[attr-defined]

    def onInstructions(self):
        """Handle Keyboard Instructions action"""
        QMessageBox.information(self, "Keyboard Instructions", self._config["readme"])

    def onClearAllPoints(self):
        """Handle Clear All Points action"""
        config = pyre.state.get_current_stos_config()
        if config is None:
            return
        sourceImageView = self._imageviewmodel_manager[ViewType.Source]
        targetImageView = self._imageviewmodel_manager[ViewType.Target]
        self.transform_controller.TransformModel = pyre.controllers.transformcontroller.CreateDefaultTransform(  # type: ignore[attr-defined]
            config.TransformType,
            sourceImageView.Image.shape,
            targetImageView.Image.shape)

    def onClearMaskedPoints(self):
        """Handle Clear Masked Points action"""
        config = pyre.state.get_current_stos_config()
        if config is None:
            return
        if not (
                config.FixedImageMaskViewModel is None or config.WarpedImageMaskViewModel is None):
            pyre.common.ClearPointsOnMask(self._transform_controller.TransformModel,
                                          config.FixedImageMaskViewModel.Image,
                                          config.WarpedImageMaskViewModel.Image)

        elif config.FixedImageMaskViewModel is not None:
            pyre.common.ClearPointsOnMask(self._transform_controller.TransformModel,
                                          config.FixedImageMaskViewModel.Image, None)  # type: ignore[arg-type]

        elif config.WarpedImageMaskViewModel is not None:
            pyre.common.ClearPointsOnMask(self._transform_controller.TransformModel, None,  # type: ignore[arg-type]
                                          config.WarpedImageMaskViewModel.Image)

    def onFlipImage(self):
        """Handle Flip Image action"""
        self.transform_controller.FlipWarped()

    def _convertTransformTo(self, transform_type: nornir_imageregistration.transforms.TransformType):
        """Convert the current transform model to the requested transform type."""
        current_transform = self._transform_controller.TransformModel
        if current_transform.type == transform_type:
            return

        kwargs = {}
        try:
            source_image = self._image_manager[ViewType.Source]
            kwargs["source_image_shape"] = source_image.shape
        except Exception:
            # Some conversion paths do not require an image shape.
            pass

        try:
            converted_transform = nornir_imageregistration.transforms.ConvertTransform(
                current_transform,
                transform_type,
                **kwargs
            )
            self._transform_controller.TransformModel = converted_transform
        except Exception as e:
            logger.exception("Failed converting transform to %s", transform_type.value)
            QMessageBox.warning(
                self,
                "Convert Transform Type",
                f"Unable to convert transform to {transform_type.value}: {e}"
            )

    def onConvertToRigid(self):
        """Convert the current transform to a rigid transform."""
        self._convertTransformTo(nornir_imageregistration.transforms.TransformType.RIGID)

    def onConvertToGrid(self):
        """Convert the current transform to a grid transform."""
        self._convertTransformTo(nornir_imageregistration.transforms.TransformType.GRID)

    def onConvertToMesh(self):
        """Convert the current transform to a mesh transform."""
        self._convertTransformTo(nornir_imageregistration.transforms.TransformType.MESH)

    def onConvertToRbf(self):
        """Convert the current transform to an RBF transform."""
        self._convertTransformTo(nornir_imageregistration.transforms.TransformType.RBF)

    def onRotateTranslate(self):
        """Handle Rotate Translate action"""
        logger.debug("Rotate translate estimate triggered")
        settings = self._settings.stos.brute_registration
        try:
            resulting_transform = pyre.common.RotateTranslateWarpedImage(source_image_key=Space.Source,  # type: ignore[arg-type]
                                                                         target_image_key=Space.Target,  # type: ignore[arg-type]
                                                                         settings=settings,
                                                                         LimitImageSize=True
                                                                         )
        except Exception as e:
            logger.exception("Rotate translate estimate failed")
            QMessageBox.warning(self, "Rotate translate estimate", str(e))
            return

        current_transform = self._transform_controller.TransformModel
        logger.debug(
            "Rotate translate estimate result_is_none=%s equals_current=%s",
            resulting_transform is None,
            resulting_transform == current_transform if resulting_transform is not None else None
        )

        if resulting_transform is not None:
            self._transform_controller.TransformModel = resulting_transform

    def onRefineGrid(self):
        """Handle Refine Grid action"""
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
        """Handle Open Fixed Image action"""
        dialog = QFileDialog(self)
        dialog.setWindowTitle("Choose a fixed image")
        dialog.setDirectory(StosWindow.imagedirname)
        dialog.setNameFilter("All files (*.*)")
        dialog.setFileMode(QFileDialog.FileMode.ExistingFile)

        if dialog.exec() == QFileDialog.DialogCode.Accepted:
            selected_files = dialog.selectedFiles()
            if selected_files:
                config = pyre.state.get_current_stos_config()
                if config is not None:
                    filename = selected_files[0]
                    StosWindow.imagedirname = os.path.dirname(filename)
                    config.LoadFixedImage(filename)  # type: ignore[attr-defined]

    def onOpenWarpedImage(self):
        """Handle Open Warped Image action"""
        dialog = QFileDialog(self)
        dialog.setWindowTitle("Choose an image to warp")
        dialog.setDirectory(StosWindow.imagedirname)
        dialog.setNameFilter("All files (*.*)")
        dialog.setFileMode(QFileDialog.FileMode.ExistingFile)

        if dialog.exec() == QFileDialog.DialogCode.Accepted:
            selected_files = dialog.selectedFiles()
            if selected_files:
                config = pyre.state.get_current_stos_config()
                if config is not None:
                    filename = selected_files[0]
                    StosWindow.imagedirname = os.path.dirname(filename)
                    config.LoadWarpedImage(filename)  # type: ignore[attr-defined]

    def onOpenFixedImageMask(self):
        """Handle Open Fixed Image Mask action"""
        dialog = QFileDialog(self)
        dialog.setWindowTitle("Choose a mask for the fixed image")
        dialog.setDirectory(StosWindow.imagedirname)
        dialog.setNameFilter("All files (*.*)")
        dialog.setFileMode(QFileDialog.FileMode.ExistingFile)

        if dialog.exec() == QFileDialog.DialogCode.Accepted:
            selected_files = dialog.selectedFiles()
            if selected_files:
                config = pyre.state.get_current_stos_config()
                if config is not None:
                    filename = selected_files[0]
                    StosWindow.imagedirname = os.path.dirname(filename)
                    config.FixedImageMaskViewModel = config.LoadFixedMaskImage(filename)  # type: ignore[attr-defined]

    def onOpenWarpedImageMask(self):
        """Handle Open Warped Image Mask action"""
        dialog = QFileDialog(self)
        dialog.setWindowTitle("Choose a mask for the warped image")
        dialog.setDirectory(StosWindow.imagedirname)
        dialog.setNameFilter("All files (*.*)")
        dialog.setFileMode(QFileDialog.FileMode.ExistingFile)

        if dialog.exec() == QFileDialog.DialogCode.Accepted:
            selected_files = dialog.selectedFiles()
            if selected_files:
                config = pyre.state.get_current_stos_config()
                if config is not None:
                    filename = selected_files[0]
                    StosWindow.imagedirname = os.path.dirname(filename)
                    config.WarpedImageMaskViewModel = config.LoadWarpedMaskImage(filename)  # type: ignore[attr-defined]

    def onOpenStos(self):
        """Handle Open Stos File action"""
        config = pyre.state.get_current_stos_config()
        dirname = config.stosdirname if config is not None else ''
        dialog = QFileDialog(self)
        dialog.setWindowTitle("Choose a file")
        dialog.setDirectory(dirname)
        dialog.setNameFilter("Stos files (*.stos)")
        dialog.setFileMode(QFileDialog.FileMode.ExistingFile)

        if dialog.exec() == QFileDialog.DialogCode.Accepted:
            selected_files = dialog.selectedFiles()
            if selected_files:
                filename = selected_files[0]
                self.dirname = os.path.dirname(filename)
                StosWindow.stosfilename = os.path.basename(filename)
                self.loadStos(filename)

    @staticmethod
    def loadStos(filename: str,
                 image_loader: IImageLoader = Provide[IContainer.image_loader],
                 stos_transform_controller: pyre.state.TransformController = Provide[
                     StosContainer.transform_controller],
                 settings: AppSettings = Provide[IContainer.settings]) -> LoadStosResult | None:
        try:
            load_result = image_loader.load_stos(filename)
            settings.stos.stos_filename = filename
            transform = nornir_imageregistration.transforms.LoadTransform(load_result.stos.Transform)  # type: ignore[arg-type]
            stos_transform_controller.TransformModel = transform

            settings.stos.source_image = ImageAndMaskPath(image_fullpath=load_result.source.image_fullpath,
                                                          mask_fullpath=load_result.source.mask_fullpath)
            settings.stos.target_image = ImageAndMaskPath(image_fullpath=load_result.target.image_fullpath,
                                                          mask_fullpath=load_result.target.mask_fullpath)

            return load_result

        except Exception as e:
            print(f"Error loading stos file: {e}")
            pass

    def onSaveWarpedImage(self):
        """Handle Save Warped Image action"""
        config = pyre.state.get_current_stos_config()
        if config is None:
            return
        if not (config.FixedImageViewModel is None or config.WarpedImageViewModel is None):
            dialog = QFileDialog(self)
            dialog.setWindowTitle("Choose a Directory")
            dialog.setDirectory(StosWindow.imagedirname)
            dialog.setNameFilter("PNG files (*.png)")
            dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)

            if dialog.exec() == QFileDialog.DialogCode.Accepted:
                selected_files = dialog.selectedFiles()
                if selected_files:
                    StosWindow.imagedirname = os.path.dirname(selected_files[0])
                    self.filename = os.path.basename(selected_files[0])
                    config.OutputImageFullPath = selected_files[0]  # type: ignore[attr-defined]

                    pool = pools.GetGlobalThreadPool()
                    pool.add_task("Save " + config.OutputImageFullPath,  # type: ignore[attr-defined]
                                  pyre.common.SaveRegisteredWarpedImage,
                                  config.OutputImageFullPath,  # type: ignore[attr-defined]
                                  config.Transform,
                                  config.WarpedImageViewModel.Image)

    def onSaveStos(self):
        """Handle Save Stos File action"""
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
                            self._settings.stos.target_image.image_fullpath,  # type: ignore[union-attr]
                            self._settings.stos.source_image.image_fullpath,  # type: ignore[union-attr]
                            self._transform_controller.TransformModel,
                            self._settings.stos.target_image.mask_fullpath,  # type: ignore[union-attr]
                            self._settings.stos.source_image.mask_fullpath, )  # type: ignore[union-attr]
                        stosObj.Save(fullpath)
                except ValueError:
                    prettyoutput.LogErr(f"Error saving stos file {fullpath}")
