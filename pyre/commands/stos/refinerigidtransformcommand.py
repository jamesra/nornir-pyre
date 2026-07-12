from __future__ import annotations

import nornir_imageregistration
from dependency_injector.wiring import Provide, inject

import pyre
from pyre.commands import InstantCommandBase
from pyre.common import RefineRigidTransformLocal
from pyre.container import IContainer
from pyre.interfaces import StatusChangeCallback
from pyre.space import Space


class RefineRigidTransformCommand(InstantCommandBase):
    """Run local STOS brute rigid refine around the current transform angle."""

    _refine_scale: bool
    _transform_controller: pyre.viewmodels.TransformController  # type: ignore[name-defined]

    @inject
    def __init__(
            self,
            refine_scale: bool = False,
            completed_func: StatusChangeCallback | None = None,
            transform_controller: pyre.viewmodels.TransformController = Provide[IContainer.transform_controller],  # type: ignore[attr-defined]
            **kwargs):
        super().__init__(completed_func=completed_func)
        self._refine_scale = refine_scale
        self._transform_controller = transform_controller

    def __str__(self) -> str:
        mode = "angle+scale" if self._refine_scale else "angle"
        return f"RefineRigidTransformCommand({mode})"

    def can_execute(self) -> bool:
        return isinstance(self._transform_controller.TransformModel, nornir_imageregistration.IRigidTransform)

    def cancel(self) -> None:
        super().cancel()

    def execute(self) -> None:
        current = self._transform_controller.TransformModel
        resulting = RefineRigidTransformLocal(
            current_transform=current,
            refine_scale=self._refine_scale,
            source_image_key=Space.Source,  # type: ignore[arg-type]
            target_image_key=Space.Target,  # type: ignore[arg-type]
        )
        if resulting is not None:
            self._transform_controller.TransformModel = resulting
        super().execute()

    def activate(self) -> None:
        super().activate()
        self.execute()
