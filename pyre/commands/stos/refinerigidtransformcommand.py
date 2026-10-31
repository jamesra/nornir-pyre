from __future__ import annotations

import nornir_imageregistration
from dependency_injector.wiring import Provide, inject

import pyre
from pyre.commands import InstantCommandBase
from pyre.common import RefineRigidTransformLocal
from pyre.container import IContainer
from pyre.commands.stos.gridregisterallcommand import _stos_window_from_manager
from pyre.interfaces import StatusChangeCallback
from pyre.interfaces.managers.window_manager import IWindowManager
from pyre.space import Space


class RefineRigidTransformCommand(InstantCommandBase):
    """Run whole-section STOS brute rigid refine seeded from the current transform."""

    _search_angle: bool
    _transform_controller: pyre.viewmodels.TransformController  # type: ignore[name-defined]
    _window_manager: IWindowManager

    @inject
    def __init__(
            self,
            search_angle: bool = False,
            completed_func: StatusChangeCallback | None = None,
            transform_controller: pyre.viewmodels.TransformController = Provide[IContainer.transform_controller],  # type: ignore[attr-defined]
            window_manager: IWindowManager = Provide[IContainer.window_manager],
            **kwargs):
        super().__init__(completed_func=completed_func)
        self._search_angle = search_angle
        self._transform_controller = transform_controller
        self._window_manager = window_manager

    def __str__(self) -> str:
        mode = "angle search" if self._search_angle else "current angle"
        return f"RefineRigidTransformCommand({mode})"

    def can_execute(self) -> bool:
        return isinstance(self._transform_controller.TransformModel, nornir_imageregistration.IRigidTransform)

    def cancel(self) -> None:
        super().cancel()

    def execute(self) -> None:
        """Submit the refine as a background job; run inline only when no STOS window exists."""
        window = _stos_window_from_manager(self._window_manager)
        if window is not None:
            window.start_rigid_refine_job(search_angle=self._search_angle)
            super().execute()
            return

        current = self._transform_controller.TransformModel
        resulting = RefineRigidTransformLocal(
            current_transform=current,
            search_angle=self._search_angle,
            source_image_key=Space.Source,  # type: ignore[arg-type]
            target_image_key=Space.Target,  # type: ignore[arg-type]
        )
        if resulting is not None:
            self._transform_controller.TransformModel = resulting
        super().execute()

    def activate(self) -> None:
        super().activate()
        self.execute()
