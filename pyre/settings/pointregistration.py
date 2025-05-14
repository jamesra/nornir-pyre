from __future__ import annotations
from dataclasses import dataclass
from typing import NamedTuple
import numpy as np
from numpy.typing import NDArray
from dependency_injector.wiring import Provide
from dependency_injector.providers import Configuration
from pyre.container import IContainer


@dataclass
class PointRegistrationSettings:
    alignment_area: NDArray[int]
    angles_to_search: NDArray[float]
    #
    # def __init__(self, alignment_area: NDArray[int], angles_to_search: NDArray[float]):
    #     self.alignment_area = alignment_area
    #     self.angles_to_search = angles_to_search
    #
    # def from_config(self, config: Configuration = Provide[IContainer]) -> PointRegistrationSettings:
    #     _alignment_area = config['alignment_tile_size']
    #     alignment_area = np.array([_alignment_area, _alignment_area], dtype=np.int32)
    #
    #     _max_alignment_angle = config['alignment_max_angle']
    #     _alignment_angle_step = config['alignment_angle_step']
    #     angles_to_search = np.arange(start=-_max_alignment_angle,
    #                                  stop=_max_alignment_angle + _alignment_angle_step,
    #                                  step=_alignment_angle_step)
    #
    #     return PointRegistrationSettings(alignment_area=alignment_area, angles_to_search=angles_to_search)
