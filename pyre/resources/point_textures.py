import os

import numpy as np

import nornir_imageregistration
import pyre
import pyre.resource_paths


def _load_point_image(path: str) -> np.ndarray:
    """
    Load a point sprite image from disk and return RGBA uint8 (H, W, 4), contiguous.
    Converts grayscale/RGB to RGBA so texture upload is correct.
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Point texture not found: {path}")
    # OpenGL texture upload needs host memory; force numpy so CuPy backend does not return GPU array
    raw = nornir_imageregistration.LoadImage(path, backend="numpy")
    if raw.ndim == 2:
        raw = np.stack([raw] * 4, axis=-1)
    elif raw.shape[-1] == 3:
        alpha = np.full((*raw.shape[:2], 1), 255, dtype=raw.dtype)
        raw = np.concatenate([raw, alpha], axis=-1)
    if raw.shape[-1] != 4:
        raise ValueError(f"Point texture {path} has shape {raw.shape}, need (H, W, 4)")
    if not np.issubdtype(raw.dtype, np.uint8):
        if np.issubdtype(raw.dtype, np.floating):
            raw = (np.clip(raw, 0, 1) * 255).astype(np.uint8)
        else:
            raw = np.clip(raw, 0, 255).astype(np.uint8)
    raw = np.ascontiguousarray(raw)
    return raw


class PointTextures:
    """
    Provides graphics for transform points
    """

    __pointImage: int | None = None
    __selectedPointImage: int | None = None
    __point_array: int | None = None
    __pointGroup = None
    __selectedPointSpriteOn = None
    __selectedPointSpriteOff = None

    __initialized: bool = False

    @property
    def PointImage(self) -> int:
        if PointTextures.__pointImage is None:
            PointTextures.LoadTextures()
        assert PointTextures.__pointImage is not None
        return PointTextures.__pointImage

    @property
    def SelectedPointImage(self) -> int:
        if PointTextures.__selectedPointImage is None:
            PointTextures.LoadTextures()
        assert PointTextures.__selectedPointImage is not None
        return PointTextures.__selectedPointImage

    @property
    def PointArray(self) -> int:
        """
        A texture array, with 0 being the unselected texture and 1 the selected texture
        :return:
        """
        assert self.__point_array is not None
        return self.__point_array

    @property
    def SelectedPointSpriteOn(self) -> int:
        if PointTextures.__selectedPointSpriteOn is None:
            PointTextures.LoadTextures()
        assert PointTextures.__selectedPointSpriteOn is not None
        return PointTextures.__selectedPointSpriteOn

    @property
    def SelectedPointSpriteOff(self) -> int:
        if PointTextures.__selectedPointSpriteOff is None:
            PointTextures.LoadTextures()
        assert PointTextures.__selectedPointSpriteOff is not None
        return PointTextures.__selectedPointSpriteOff

    @classmethod
    def LoadTextures(cls):
        if not cls.__initialized:
            res = pyre.resource_paths.ResourcePath()
            point_image = _load_point_image(os.path.join(res, "Point.png"))
            cls.__pointImage = pyre.gl_engine.create_rgba_texture(point_image)

            selected_image = _load_point_image(os.path.join(res, "SelectedPoint.png"))
            cls.__selectedPointImage = pyre.gl_engine.create_rgba_texture(selected_image)

            cls.__selectedPointSpriteOn = cls.__selectedPointImage
            cls.__selectedPointSpriteOff = cls.__pointImage

            array_image = np.array([point_image, selected_image], dtype=np.uint8)
            cls.__point_array = pyre.gl_engine.create_rgba_texture_array(array_image)

            cls.__initialized = True

        #     cls.__pointImage = pyglet.image.load(os.path.join(pyre.resources.ResourcePath(), "Point.png"))
        #     cls.__pointImage.anchor_x = cls.__pointImage.width // 2
        #     cls.__pointImage.anchor_y = cls.__pointImage.height // 2
        #
        # if cls.__selectedPointImage is None:
        #     cls.__selectedPointImage = pyglet.image.load(
        #         os.path.join(pyre.resources.ResourcePath(), "SelectedPoint.png"))
        #     cls.__selectedPointImage.anchor_x = cls.__selectedPointImage.width // 2
        #     cls.__selectedPointImage.anchor_y = cls.__selectedPointImage.height // 2
        #
        # if cls.__pointGroup is None:
        #     cls.__pointGroup = pyglet.sprite.SpriteGroup(texture=cls.__pointImage.get_texture(),
        #                                                  blend_src=pyglet.gl.GL_SRC_ALPHA,
        #                                                  blend_dest=pyglet.gl.GL_ONE_MINUS_SRC_ALPHA,
        #                                                  program=pyglet.sprite.get_default_shader())
        #     cls.__selectedPointSpriteOn = pyglet.sprite.Sprite(cls.__selectedPointImage, 0, 0, group=cls.__pointGroup)
        #     cls.__selectedPointSpriteOff = pyglet.sprite.Sprite(cls.__pointImage, 0, 0, group=cls.__pointGroup)


def load_point_textures():
    PointTextures.LoadTextures()
