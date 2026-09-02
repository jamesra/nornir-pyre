from __future__ import annotations

from typing import TYPE_CHECKING

from dependency_injector.wiring import Provide, inject
from nornir_imageregistration.transforms.transform_type import TransformType
from PyQt6.QtWidgets import QMessageBox, QWidget

import pyre
from pyre.commands import InstantCommandBase
from pyre.container import IContainer
from pyre.interfaces import StatusChangeCallback
from pyre.interfaces.managers import IImageManager
from pyre.interfaces.managers.window_manager import IWindowManager
from pyre.interfaces.viewtype import ViewType
from pyre.settings import AppSettings
from pyre.ui.windows.refine_grid_settings_dialog import RefineGridSettingsDialog

if TYPE_CHECKING:
    from pyre.ui.windows.stoswindow import StosWindow


def _stos_window_from_manager(window_manager: IWindowManager) -> StosWindow | None:
    """Return the first STOS window in *window_manager*, if any."""
    from pyre.ui.windows.stoswindow import StosWindow

    for view_type in (ViewType.Source, ViewType.Target, ViewType.Composite):
        if view_type not in window_manager:
            continue
        win = window_manager[view_type]
        if isinstance(win, StosWindow):
            return win
    return None


class GridRegisterAllCommand(InstantCommandBase):
    """Prompt for one-pass grid refine settings and run RefineTransform.

    Shift+Space is a single ``num_iterations=1`` job. Menu Refine w/ Grid
    passes the dialog iteration count through the same helper; repeating this
    command N times is not equivalent to one N-pass refine.
    """

    _parent: QWidget | None
    _transform_controller: pyre.viewmodels.TransformController  # type: ignore[name-defined]
    _image_manager: IImageManager
    _window_manager: IWindowManager
    _app_settings: AppSettings

    @inject
    def __init__(
            self,
            completed_func: StatusChangeCallback | None = None,
            parent: QWidget | None = None,
            transform_controller: pyre.viewmodels.TransformController = Provide[IContainer.transform_controller],  # type: ignore[attr-defined]
            image_manager: IImageManager = Provide[IContainer.image_manager],
            window_manager: IWindowManager = Provide[IContainer.window_manager],
            settings: AppSettings = Provide[IContainer.settings],
            **kwargs):
        super().__init__(completed_func=completed_func)
        self._parent = parent
        self._transform_controller = transform_controller
        self._image_manager = image_manager
        self._window_manager = window_manager
        self._app_settings = settings

    def __str__(self) -> str:
        return "GridRegisterAllCommand"

    def can_execute(self) -> bool:
        return self._transform_controller.type == TransformType.GRID

    def cancel(self) -> None:
        super().cancel()

    def execute(self) -> None:
        """Show the one-pass refine dialog and submit the shared CPU refine job."""
        if (self._app_settings.stos.source_image is None
                or self._app_settings.stos.target_image is None):
            print("Need both images loaded with a transform to run refine grid")
            super().execute()
            return

        user_settings = RefineGridSettingsDialog.GetGridRefineSettings(
            self._parent,
            app_settings=self._app_settings,
            fixed_num_iterations=1,
        )
        if user_settings is None:
            super().execute()
            return

        window = _stos_window_from_manager(self._window_manager)
        if window is None:
            QMessageBox.warning(
                self._parent,
                "Grid refine (one pass)",
                "No STOS window is available to run grid refinement.",
            )
            super().execute()
            return

        window.start_grid_refine_job(
            user_settings,
            title="Grid refine (one pass)",
            save_plots=False,
        )
        super().execute()

    def activate(self) -> None:
        super().activate()
        self.execute()
