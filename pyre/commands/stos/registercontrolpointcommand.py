from __future__ import annotations
from typing import Sequence, Iterable
from dependency_injector.wiring import inject, Provide
from dependency_injector.providers import Configuration
import numpy as np
from numpy._typing import NDArray
import wx
from pyre.observable import ObservableSet, ObservedAction
from nornir_imageregistration import ImagePermutationHelper
import nornir_pools as pools
import math

import nornir_imageregistration
import pyre
from pyre import Space
from pyre.command_interfaces import StatusChangeCallback
from pyre.commands import InstantCommandBase, NavigationCommandBase
from pyre.interfaces.managers import ICommandQueue, IMousePositionHistoryManager, IImageManager
from pyre.interfaces.controlpointselection import SetSelectionCallable
from pyre.container import IContainer
from pyre.commands.commandexceptions import RequiresSelectionError


class RegisterControlPointCommand(InstantCommandBase):
    """Automatically register selected control points"""

    _selected_points: ObservableSet[int]  # The indices of the selected points
    _original_points: NDArray[[2, ], np.floating]
    _transform_controller: pyre.viewmodels.TransformController
    _image_manager: IImageManager = Provide[IContainer.image_manager]
    _source_image: str
    _target_image: str

    @property
    def alignment_area(self) -> NDArray[int]:
        side = self._config['alignment_tile_size']
        return np.array([side, side], dtype=np.int32)

    @property
    def angles_to_search(self) -> NDArray[float]:
        max_angle = self._config['alignment_max_search_angle']
        angle_step = self._config['alignment_search_angle_step']

        angles = np.arange(start=-max_angle,
                           stop=max_angle + angle_step,
                           step=angle_step)  # numpy.linspace(-7.5, 7.5, 11)
        return angles

    @inject
    def __init__(self,
                 selected_points: ObservableSet[int],  # The indices of the selected points
                 command_points: set[int],  # Points under mouse when command was triggered
                 source_image: str,
                 target_image: str,
                 completed_func: StatusChangeCallback = None,
                 register_all: bool = False,  # If True, register all points in the transform
                 transform_controller: pyre.viewmodels.TransformController = Provide[IContainer.transform_controller],
                 config: Configuration = Provide[IContainer.config],
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

        if register_all:
            self._selected_points.update(range(transform_controller.NumPoints))
        else:
            self._selected_points.update(command_points)

        if len(self._selected_points) == 0:
            raise RequiresSelectionError('No points selected')

        self._original_points = transform_controller.points
        self._transform_controller = transform_controller

    def __str__(self):
        return "RegisterControlPointCommand"

    def can_execute(self) -> bool:
        return True

    def cancel(self):
        super().cancel()
        return

    def execute(self):
        source = self._image_manager[self._source_image]
        target = self._image_manager[self._target_image]

        indicies_to_register = list(self._selected_points)
        # self.SelectedPointIndex = self._transform_controller.AutoAlignPoints(self.indicies_to_register)
        self.align_points(source, target, self._selected_points)

        self._selected_points.clear()
        super().execute()

    def activate(self):
        super().activate()
        self.execute()

    def align_points(self,
                     sourceimage: ImagePermutationHelper,
                     targetimage: ImagePermutationHelper,
                     i_points: Sequence[int]) -> None:
        """Attemps to align the specified point indicies"""
        # from pyre.state import currentStosConfig

        # if (currentStosConfig.FixedImageViewModel is None or
        #         currentStosConfig.WarpedImageViewModel is None):
        #     return

        if isinstance(i_points, range):
            i_points = list(i_points)
        elif isinstance(i_points, Iterable) and not isinstance(i_points, Sequence):
            i_points = [*i_points]
        elif not isinstance(i_points, Iterable):
            i_points = [i_points]

        offsets = np.zeros((self._transform_controller.NumPoints, 2))

        indextotask = {}
        invalid_points = []
        if len(i_points) > 1:
            pool = pools.GetGlobalLocalMachinePool()

            for i_point in i_points:
                fixed = self._transform_controller.GetFixedPoint(i_point)
                warped = self._transform_controller.GetWarpedPoint(i_point)

                task = pyre.common.StartAttemptAlignPoint(pool=pool,
                                                          task_description=f"Align Pyre Point {i_point}",
                                                          transform=self._transform_controller.TransformModel,
                                                          target_image=targetimage.ImageWithMaskAsNoise,
                                                          source_image=sourceimage.ImageWithMaskAsNoise,
                                                          target_mask=targetimage.BlendedMask,
                                                          source_mask=sourceimage.BlendedMask,
                                                          target_image_stats=sourceimage.Stats,
                                                          source_image_stats=targetimage.Stats,
                                                          target_controlpoint=fixed,
                                                          alignmentArea=self.alignment_area,
                                                          anglesToSearch=self.angles_to_search)

                if task is not None:
                    indextotask[i_point] = task
                else:
                    invalid_points.append(i_point)

            for i_point in sorted(indextotask.keys()):
                task = indextotask[i_point]

                record = None
                try:
                    record = task.wait_return()
                except Exception as e:
                    print(f"Exception aligning point {i_point}:\n{e}")
                    return

                if record is None:
                    print("point #" + str(i_point) + " returned None for alignment")
                    continue

                if record.weight == 0:
                    print("point #" + str(i_point) + " returned weight 0 for alignment, ignoring")
                    continue

                (dy, dx) = record.peak

                if math.isnan(dx) or math.isnan(dy):
                    continue

                offsets[i_point, :] = np.array([dy, dx])
                del indextotask[i_point]

        else:
            i_point = i_points
            fixed = self._transform_controller.GetFixedPoint(i_point)
            warped = self._transform_controller.GetWarpedPoint(i_point)
            task = pyre.common.StartAttemptAlignPoint(pool=pools.GetGlobalLocalMachinePool(),
                                                      task_description=f"Align Pyre Point {i_point}",
                                                      transform=self._transform_controller.TransformModel,
                                                      target_image=targetimage.ImageWithMaskAsNoise,
                                                      source_image=sourceimage.ImageWithMaskAsNoise,
                                                      target_mask=targetimage.BlendedMask,
                                                      source_mask=sourceimage.BlendedMask,
                                                      target_image_stats=sourceimage.Stats,
                                                      source_image_stats=targetimage.Stats,
                                                      target_controlpoint=fixed,
                                                      alignmentArea=self.alignment_area,
                                                      anglesToSearch=self.angles_to_search)

            if task is None:
                print("point #" + str(i_point) + " had no texture for alignment")
                return

            record = None
            try:
                record = task.wait_return()
            except Exception as e:
                print(f"Exception aligning point {i_point}:\n{e}")
                return

            if record is None:
                print("point #" + str(i_point) + " returned None for alignment")
                return

            if record.weight == 0:
                print("point #" + str(i_point) + " returned weight 0 for alignment, ignoring")
                return

            (dy, dx) = record.peak

            if math.isnan(dx) or math.isnan(dy):
                return

            print(f"Adjusting point {i_point} by x: {dx} y: {dy}")
            offsets[i_point, :] = np.array([dy, dx])

        # Translate all points
        self._transform_controller.TranslateFixed(offsets)

        # If we aligned all points, remove the ones we couldn't register
        self._transform_controller.RemovePoints(invalid_points)

        # return self._transform_controller.MovePoint(i_point, dx, dy, FixedSpace = self.FixedSpace)
