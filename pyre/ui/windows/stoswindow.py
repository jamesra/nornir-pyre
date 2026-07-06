import os
import logging
import numpy as np

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
from pyre.interfaces.managers.window_manager import IWindowManager
import pyre.state
from pyre.interfaces.viewtype import ViewType
from pyre.interfaces.named_tuples import LoadStosResult
import pyre.ui
from pyre.ui.widgets import ImageTransformViewPanel
from pyre.ui.windows.filedrop import FileDrop
from pyre.ui.windows.help_dialog import ControlsHelpDialog
from pyre.ui.window_geometry import apply_saved_browser_geometry
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
    _folder_browser: 'StosFileBrowserWindow | None' = None  # shared across all StosWindow instances
    _selected_points: ObservableSet[int] = Provide[StosContainer.selected_points]
    _transform_controller: pyre.state.TransformController
    _imageviewmodel_manager: IImageViewModelManager = Provide[IContainer.image_viewmodel_manager]
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
        self._space = Space.Source if view_type in (ViewType.Source, ViewType.Composite) else Space.Target
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

        # Show the window
        self.show()

    @classmethod
    def sync_window_visibility_menus(cls, window_manager: IWindowManager) -> None:
        """Update Windows menu checkmarks to match each view's visibility."""
        try:
            source_visible = window_manager[ViewType.Source].isVisible()
            target_visible = window_manager[ViewType.Target].isVisible()
            composite_visible = window_manager[ViewType.Composite].isVisible()
        except KeyError:
            return
        for view_type in (ViewType.Source, ViewType.Target, ViewType.Composite):
            win = window_manager[view_type]
            if not isinstance(win, StosWindow):
                continue
            win.menuShowFixedImage.setChecked(target_visible)  # type: ignore[union-attr]
            win.menuShowWarpedImage.setChecked(source_visible)  # type: ignore[union-attr]
            win.menuShowCompositeImage.setChecked(composite_visible)  # type: ignore[union-attr]

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

        menuInstructions = menu.addAction("&Mouse and Keyboard Help")
        menuInstructions.triggered.connect(self.onInstructions)  # type: ignore[union-attr]

        menuClearMasked = menu.addAction("&Clear All Masked points")
        menuClearMasked.triggered.connect(self.onClearMaskedPoints)  # type: ignore[union-attr]

        menuClear = menu.addAction("&Reset Transform")
        menuClear.triggered.connect(self.onResetTransform)  # type: ignore[union-attr]

        return menu

    def __createFileMenu(self):
        """Create the File menu"""
        filemenu = QMenu("&File", self)

        # Open stos action
        menuOpenStos = filemenu.addAction("&Open stos file")
        menuOpenStos.triggered.connect(self.onOpenStos)  # type: ignore[union-attr]

        # Open stos folder browser
        menuOpenStosBrowser = filemenu.addAction("Open Stos &Folder Browser\u2026")
        menuOpenStosBrowser.triggered.connect(self.onOpenStosFolderBrowser)  # type: ignore[union-attr]

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

    def _set_layout_position(self, position, desired_displays: int = 1):
        """Position all rendering windows then, if the folder browser is visible,
        tuck it to the left of the composite window at its current width."""
        super()._set_layout_position(position, desired_displays)
        if StosWindow._folder_browser is not None and StosWindow._folder_browser.isVisible():
            self._position_folder_browser_beside_composite()

    def _position_folder_browser_beside_composite(self):
        """Move the folder browser to the left of the composite window and shrink
        the composite by the browser's width so they sit flush without overlap."""
        browser = StosWindow._folder_browser
        if browser is None or not browser.isVisible():
            return
        if ViewType.Composite not in self._window_manager:
            return
        composite_win = self._window_manager[ViewType.Composite]
        geom = composite_win.geometry()
        browser_w = browser.width()
        if geom.width() <= browser_w:
            return  # composite too narrow to split — leave as-is
        browser.move(geom.x(), geom.y())
        browser.resize(browser_w, geom.height())
        composite_win.move(geom.x() + browser_w, geom.y())
        composite_win.resize(geom.width() - browser_w, geom.height())

    def onRestoreOrientation(self):
        """Handle Restore Orientation action"""
        self._window_manager[ViewType.Composite.value].setPosition()  # type: ignore[attr-defined]
        self._window_manager[ViewType.Target.value].setPosition()  # type: ignore[attr-defined]
        self._window_manager[ViewType.Source.value].setPosition()  # type: ignore[attr-defined]

    def onInstructions(self):
        """Open scrollable help scrolled to mouse and keyboard controls."""
        ControlsHelpDialog(self, self._config["readme"]).exec()

    def onResetTransform(self):
        """Reset the transform. Rigid transforms return to zero offset and angle."""
        config = pyre.state.get_current_stos_config()
        if config is None:
            return
        transform_type = config.TransformType or nornir_imageregistration.transforms.TransformType.RIGID
        if transform_type == nornir_imageregistration.transforms.TransformType.RIGID:
            self.transform_controller.reset_rigid_transform()
            self.imagepanel._glpanel.update()
            return

        source_key = ViewType.Source.value
        target_key = ViewType.Target.value
        manager = self._imageviewmodel_manager
        if source_key not in manager or target_key not in manager:
            QMessageBox.warning(
                self,
                "Reset Transform",
                "Load fixed and warped images before resetting a mesh transform.",
            )
            return
        source_image_view = manager[source_key]
        target_image_view = manager[target_key]
        self.transform_controller.TransformModel = pyre.controllers.transformcontroller.CreateDefaultTransform(  # type: ignore[attr-defined]
            transform_type,
            source_image_view.Image.shape,
            target_image_view.Image.shape)
        self.imagepanel._glpanel.update()

    def onClearAllPoints(self):
        """Deprecated alias for onResetTransform."""
        self.onResetTransform()

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
        current_transform = self._transform_controller.TransformModel
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
                    config.LoadFixedImage(filename)

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
                    config.LoadWarpedImage(filename)

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
                    config.FixedImageMaskViewModel = config.LoadFixedMaskImage(filename)

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
                    config.WarpedImageMaskViewModel = config.LoadWarpedMaskImage(filename)

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
                self.loadStos(filename, browser_folder=None, browser_flat_manual=False)
                if StosWindow._folder_browser is not None:
                    StosWindow._folder_browser.set_current_file(filename)

    @classmethod
    def _ensure_folder_browser(cls) -> 'StosFileBrowserWindow':
        """Create the shared folder browser window if needed."""
        from pyre.ui.windows.stosfilebrowser import StosFileBrowserWindow
        if cls._folder_browser is None:
            cls._folder_browser = StosFileBrowserWindow(parent=None)
        return cls._folder_browser

    @classmethod
    def show_folder_browser(cls, anchor_window: 'StosWindow | None' = None,
                            settings: AppSettings | None = None) -> None:
        """Show the shared folder browser and optionally dock it beside the composite view."""
        browser = cls._ensure_folder_browser()
        browser.show()
        browser.raise_()
        browser.activateWindow()
        if settings is None and anchor_window is not None:
            settings = anchor_window._settings
        if settings is not None and apply_saved_browser_geometry(settings, browser, force_visible=True):
            return
        if anchor_window is not None:
            anchor_window._position_folder_browser_beside_composite()

    @classmethod
    def open_folder_browser_if_cached_folder_exists(
            cls,
            settings: AppSettings,
            anchor_window: 'StosWindow',
            *,
            geometry_restored: bool = False,
    ) -> None:
        """Show the browser at startup when a saved folder path still exists."""
        del geometry_restored  # kept for call-site compatibility
        from pyre.ui.windows.stosfilebrowser import StosFileBrowserWindow
        if not StosFileBrowserWindow.has_cached_folder(settings):
            return
        browser = cls._ensure_folder_browser()
        last_loaded = settings.stos.stos_fullpath
        if last_loaded:
            browser.set_current_file(last_loaded)
        browser.show()
        browser.raise_()
        restored_saved = apply_saved_browser_geometry(settings, browser, force_visible=True)
        # #region agent log
        import json as _json, time as _time
        try:
            composite = anchor_window._window_manager.get(ViewType.Composite)
            with open(r"d:\src\git\nornir\debug-203327.log", "a", encoding="utf-8") as _f:
                _f.write(_json.dumps({
                    "sessionId": "203327", "hypothesisId": "B",
                    "location": "stoswindow.py:open_folder_browser_if_cached_folder_exists",
                    "message": "startup browser placement",
                    "data": {
                        "restored_saved_geometry": restored_saved,
                        "browser_x": browser.x(),
                        "browser_y": browser.y(),
                        "composite_x": None if composite is None else composite.x(),
                    },
                    "timestamp": int(_time.time() * 1000),
                }) + "\n")
        except Exception:
            pass
        # #endregion
        if restored_saved:
            return
        anchor_window._position_folder_browser_beside_composite()

    def onOpenStosFolderBrowser(self):
        """Show (or create) the Stos Folder Browser window."""
        StosWindow.show_folder_browser(anchor_window=self)

    @classmethod
    def close_folder_browser(cls) -> None:
        """Close the shared Stos file browser window, if it is open."""
        browser = cls._folder_browser
        if browser is None:
            return
        browser.close()
        cls._folder_browser = None

    def onExit(self):
        """Exit the application; folder-browser geometry is captured on aboutToQuit."""
        super().onExit()

    @staticmethod
    def loadStos(filename: str,
                 image_loader: IImageLoader = Provide[IContainer.image_loader],
                 stos_transform_controller: pyre.state.TransformController = Provide[
                     StosContainer.transform_controller],
                 settings: AppSettings = Provide[IContainer.settings],
                 browser_folder: str | None = None,
                 browser_flat_manual: bool = False) -> LoadStosResult | None:
        try:
            load_result = image_loader.load_stos(filename)
            settings.stos.stos_filename = filename
            settings.stos.stos_opened_from_browser_folder = browser_folder
            settings.stos.stos_browser_flat_manual = browser_flat_manual
            transform = nornir_imageregistration.transforms.LoadTransform(load_result.stos.Transform)  # type: ignore[arg-type]
            stos_transform_controller.TransformModel = transform

            settings.stos.source_image = ImageAndMaskPath(image_fullpath=load_result.source.image_fullpath,
                                                          mask_fullpath=load_result.source.mask_fullpath)
            settings.stos.target_image = ImageAndMaskPath(image_fullpath=load_result.target.image_fullpath,
                                                          mask_fullpath=load_result.target.mask_fullpath)
            stos_config = pyre.state.get_current_stos_config()
            if stos_config is not None:
                from pyre.stos_registration import resolve_warped_and_fixed_image_data, sync_stos_registration_roles
                warped, fixed = resolve_warped_and_fixed_image_data(
                    image_loader._image_manager,  # type: ignore[attr-defined]
                    ViewType.Source.value,
                    ViewType.Target.value,
                    stos_filename=filename,
                    settings_source_image_path=load_result.source.image_fullpath,
                    settings_target_image_path=load_result.target.image_fullpath,
                )
                sync_stos_registration_roles(stos_config, warped, fixed)

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

            browser_folder = self._settings.stos.stos_opened_from_browser_folder
            if browser_folder:
                from pyre.stos_manual_paths import ensure_manual_directory
                if self._settings.stos.stos_browser_flat_manual:
                    dirname = browser_folder
                else:
                    dirname = ensure_manual_directory(browser_folder)

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
                        if StosWindow._folder_browser is not None:
                            StosWindow._folder_browser.rescan()
                            StosWindow._folder_browser.set_current_file(fullpath)
                except ValueError:
                    prettyoutput.LogErr(f"Error saving stos file {fullpath}")
