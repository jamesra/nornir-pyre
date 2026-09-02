from __future__ import annotations

from dependency_injector.wiring import inject, Provide
from dependency_injector.providers import Configuration
import logging
import numpy as np
from numpy._typing import NDArray
from pyre.observable import ObservableSet
from nornir_imageregistration import ImagePermutationHelper

import pyre
from pyre.image_contrast import contrasted_permutation_helper
from pyre.interfaces import StatusChangeCallback
from pyre.commands import InstantCommandBase
from pyre.interfaces.managers import IImageManager
from pyre.container import IContainer
from pyre.commands.commandexceptions import RequiresSelectionError
from pyre.settings import AppSettings, PointRegistrationSettings

_logger = logging.getLogger(__name__)


class RegisterControlPointCommand(InstantCommandBase):
    """Enqueue automatic registration for selected control points."""

    _selected_points: ObservableSet[int]  # The indices of the selected points
    _original_points: NDArray[np.floating]
    _transform_controller: pyre.viewmodels.TransformController  # type: ignore[attr-defined]
    _image_manager: IImageManager = Provide[IContainer.image_manager]
    _source_image: str
    _target_image: str
    _app_settings: AppSettings
    _settings: PointRegistrationSettings

    @property
    def alignment_area(self) -> NDArray[np.integer]:
        return self._settings.alignment_area_shape

    @property
    def angles_to_search(self) -> NDArray[np.floating]:
        return self._settings.angles_to_search

    @property
    def estimate_angle(self) -> bool:
        return self._settings.estimate_angle

    @inject
    def __init__(self,
                 selected_points: ObservableSet[int],  # The indices of the selected points
                 command_points: set[int],  # Points under mouse when command was triggered
                 source_image: str,
                 target_image: str,
                 completed_func: StatusChangeCallback | None = None,  # type: ignore[assignment]
                 register_all: bool = False,  # If True, register all points in the transform
                 transform_controller: pyre.viewmodels.TransformController = Provide[IContainer.transform_controller],  # type: ignore[attr-defined]
                 config: Configuration = Provide[IContainer.config],
                 settings: AppSettings = Provide[IContainer.settings],
                 **kwargs):

        """

        :param parent:
        :param transform_controller:
        :param camera:
        :param bounds:
        :param translate_origin:  Where the mouse was when the translation started
        :param selected_points:
        :param space:
        :param completed_func:
        """
        super().__init__(completed_func=completed_func)

        self._config = config
        self._source_image = source_image
        self._target_image = target_image
        self._selected_points = selected_points
        self._app_settings = settings
        self._settings = settings.stos.point_registration

        if register_all:
            self._selected_points.update(range(transform_controller.NumPoints))
            self._original_points = transform_controller.points
        else:
            self._selected_points.update(command_points)
            self._original_points = transform_controller.points

        if len(self._selected_points) == 0:
            raise RequiresSelectionError('No points selected')

        self._transform_controller = transform_controller

    def __str__(self):
        return "RegisterControlPointCommand"

    def can_execute(self) -> bool:
        return True

    def cancel(self):
        super().cancel()
        return

    def execute(self):
        queued = list(self._selected_points)
        # Images published to shared memory at load (and on contrast settle) are
        # already the arrays the pool workers attach to; re-wrapping them here
        # would build a helper the controller cannot match to a publication.
        published = bool(getattr(
            self._transform_controller, "registration_images_published", False)
            or getattr(
            self._transform_controller, "registration_publish_pending", False))
        source = None
        target = None
        if not published:
            source = contrasted_permutation_helper(
                self._image_manager[self._source_image],
                self._app_settings.ui.source_contrast,
            )
            target = contrasted_permutation_helper(
                self._image_manager[self._target_image],
                self._app_settings.ui.target_contrast,
            )
        self._transform_controller.enqueue_point_registrations(
            queued,
            source_image=source,
            target_image=target,
            alignment_area=self.alignment_area,
            angles_to_search=self.angles_to_search,
            estimate_angle=self.estimate_angle,
        )
        # Enumerates every index actually queued (not just the count) plus its session ID,
        # to check whether _selected_points has accumulated stale entries from earlier
        # selections instead of holding only the point the user just clicked.
        queued_ids = [(index, self._transform_controller.point_id_for_index(index)) for index in queued]
        _logger.info("RegisterControlPointCommand queued %s selected point(s): %s", len(queued), queued_ids)
        super().execute()

    def activate(self):
        super().activate()
        self.execute()

    def align_points(self,
                     sourceimage: ImagePermutationHelper,
                     targetimage: ImagePermutationHelper,
                     i_points: list[int]) -> None:
        """Enqueue alignments for *i_points* using the provided images."""
        self._transform_controller.enqueue_point_registrations(
            i_points,
            source_image=sourceimage,
            target_image=targetimage,
            alignment_area=self.alignment_area,
            angles_to_search=self.angles_to_search,
            estimate_angle=self.estimate_angle,
        )
