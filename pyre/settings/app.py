from collections.abc import Iterable
import os
# import yaml
from fontTools.qu2cu.qu2cu import Point
from pydantic import BaseModel
from dataclasses import dataclass, field
import numpy as np
from numpy.typing import NDArray

import nornir_imageregistration.settings
from nornir_imageregistration.settings.stos_brute import StosBruteSettings


class AngleSearchRange(BaseModel):
    max_angle: float = 7.5  # Maximum +/- deflection angle to rotate images when searching for the best control point alignment
    angle_step_size: float = 3  # Number of degrees to step between search angles

    def __init__(self, max_angle: float = 7.5, angle_step_size: float = 3):
        super().__init__(max_angle=max_angle, angle_step_size=angle_step_size)

    @staticmethod
    def zero():
        """An angle search range with only 0 degrees"""
        return AngleSearchRange(max_angle=0, angle_step_size=1)

    @property
    def angle_range(self) -> NDArray[float]:
        angles = np.arange(start=-self.max_angle,
                           stop=self.max_angle + self.angle_step_size,
                           step=self.angle_step_size)  # numpy.linspace(-7.5, 7.5, 11)
        angles = np.union1d(angles, [0])
        return angles

    def __iter__(self):
        return iter(self.angle_range)


class PointRegistrationSettings(BaseModel):
    alignment_area: int = 128
    angle_search_range: AngleSearchRange = AngleSearchRange.zero()  # field(default_factory=AngleSearchRange)

    def __init__(self, alignment_area: int = 256, angle_search_range: AngleSearchRange = AngleSearchRange.zero()):
        super().__init__(alignment_area=alignment_area, angle_search_range=angle_search_range)

    @property
    def alignment_area_shape(self) -> NDArray[int]:
        side = self.alignment_area
        return np.array([side, side], dtype=np.int32)

    @property
    def angles_to_search(self) -> NDArray[float]:
        return self.angle_search_range.angle_range


class ImageAndMaskPath(BaseModel):
    image_fullpath: str  # Full path to the image or None if it doesn't exist
    mask_fullpath: str | None  # Full path to the mask or None if it doesn't exist


class StosSettings(BaseModel):
    stos_dirname: str | None = None  # The last directory loaded or saved by the user
    stos_filename: str | None = None  # The last filename loaded or saved by the user
    grid_registration: PointRegistrationSettings = PointRegistrationSettings(
        angle_search_range=AngleSearchRange(max_angle=7.5,
                                            angle_step_size=2.5))  # field(default_factory=PointRegistrationSettings)
    brute_registration: StosBruteSettings = StosBruteSettings(
        method=nornir_imageregistration.settings.SliceToSliceMethod.LogPolar)  # field(default_factory=StosBruteSettings)
    point_registration: PointRegistrationSettings = PointRegistrationSettings()  # Used when the user selects a single point to register
    source_image: ImageAndMaskPath | None = None  # The last source image loaded by the user
    target_image: ImageAndMaskPath | None = None  # The last target image loaded by the user

    @property
    def stos_fullpath(self) -> str | None:
        if self.stos_dirname is not None and self.stos_filename is not None:
            return os.path.join(self.stos_dirname, self.stos_filename)
        elif self.stos_filename is not None:
            return self.stos_filename


class FloatRange(BaseModel):
    max: float
    min: float


class UISettings(BaseModel):
    zoom_limits: FloatRange = FloatRange(min=0.00390625, max=16)  # Maximum and minimum zoom levels
    control_point_search_radius: float = 10.0  # Radius in pixels to search for control points
    image_search_paths: list[str] = []  # field(default_factory=list)  # Paths to search for images
    replacement_paths: dict[
        str, str] = {}  # field(default_factory=dict)  # Paths to try replacing when searching for files


class AppSettings(BaseModel):
    debug: bool = False
    readme: str = "README.txt"

    ui: UISettings = UISettings()  # field(default_factory=UISettings)
    stos: StosSettings = StosSettings()  # field(default_factory=StosSettings)
