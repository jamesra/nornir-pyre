import os
# import yaml
from fontTools.qu2cu.qu2cu import Point
from pydantic import BaseModel
from dataclasses import dataclass, field


class AngleSearchRange(BaseModel):
    max_search_angle: float = 7.5  # Maximum +/- deflection angle to rotate images when searching for the best control point alignment
    search_angle_step_size: float = 3  # Number of degrees to step between search angles


class PointRegistrationSettings(BaseModel):
    alignment_area: int = 128
    angles_to_search: AngleSearchRange = AngleSearchRange()  # field(default_factory=AngleSearchRange)


class ImageAndMaskPath(BaseModel):
    image_fullpath: str  # Full path to the image or None if it doesn't exist
    mask_fullpath: str | None  # Full path to the mask or None if it doesn't exist


class StosSettings(BaseModel):
    stos_dirname: str | None = None  # The last directory loaded or saved by the user
    stos_filename: str | None = None  # The last filename loaded or saved by the user
    registration: PointRegistrationSettings = PointRegistrationSettings()  # field(default_factory=PointRegistrationSettings)
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


class AppSettings(BaseModel):
    debug: bool = False
    readme: str = "README.txt"

    ui: UISettings = UISettings()  # field(default_factory=UISettings)
    stos: StosSettings = StosSettings()  # field(default_factory=StosSettings)
