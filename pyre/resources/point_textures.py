import os

import numpy as np

import nornir_imageregistration
import pyre
import pyre.resource_paths


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

        return PointTextures.__pointImage

    @property
    def SelectedPointImage(self) -> int:
        if PointTextures.__selectedPointImage is None:
            PointTextures.LoadTextures()

        return PointTextures.__selectedPointImage

    @property
    def PointArray(self) -> int:
        """
        A texture array, with 0 being the unselected texture and 1 the selected texture
        :return:
        """
        return self.__point_array

    @property
    def SelectedPointSpriteOn(self) -> int:
        if PointTextures.__selectedPointSpriteOn is None:
            PointTextures.LoadTextures()

        return PointTextures.__selectedPointSpriteOn

    @property
    def SelectedPointSpriteOff(self) -> int:
        if PointTextures.__selectedPointSpriteOff is None:
            PointTextures.LoadTextures()

        return PointTextures.__selectedPointSpriteOff

    @classmethod
    def LoadTextures(cls):
        if not cls.__initialized:
            image_path = os.path.join(pyre.resource_paths.ResourcePath(), "Point.png")
            point_image = nornir_imageregistration.LoadImage(image_path)
            cls.__pointImage = pyre.gl_engine.create_rgba_texture(point_image)

            selected_image_path = os.path.join(pyre.resource_paths.ResourcePath(), "SelectedPoint.png")
            selected_image = nornir_imageregistration.LoadImage(selected_image_path)
            cls.__selectedPointImage = pyre.gl_engine.create_rgba_texture(selected_image)

            cls.__selectedPointSpriteOn = cls.__selectedPointImage
            cls.__selectedPointSpriteOff = cls.__pointImage

            array_image = np.array([point_image, selected_image])
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
