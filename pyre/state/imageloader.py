import concurrent.futures
from enum import Enum
import os

from nornir_imageregistration import StosFile
import nornir_imageregistration.transforms
from pyre.state import IImageManager, IImageViewModelManager
from pyre.resources import try_locate_file
from pyre.state.viewtype import ViewType
from pyre.viewmodels import ImageViewModel, TransformController


class ImageLoader:
    """Loads images and creates viewmodels for them."""
    _transform_controller: TransformController
    _image_manager: IImageManager
    _image_viewmodel_manager: IImageViewModelManager
    _search_dirs: list[str] | None

    def __init__(self,
                 transform_controller: TransformController,
                 image_manager: IImageManager,
                 imageviewmodel_manager: IImageViewModelManager,
                 search_dirs: list[str] | None = None
                 ):
        self._transform_controller = transform_controller
        self._image_manager = image_manager
        self._image_viewmodel_manager = imageviewmodel_manager
        self._search_dirs = search_dirs

    def load_stos(self,
                  stos_path: str) -> nornir_imageregistration.ITransform:
        """Loads a stos file and the images it references."""
        obj = StosFile.Load(stos_path)

        search_paths = list(self._search_dirs) if self._search_dirs is not None else []
        search_paths.append(os.path.dirname(stos_path))

        # source_key, source_permutations = self.load_image_into_manager(key=ViewType.Source.value,
        #                                                                image_path=obj.ControlImageFullPath,
        #                                                                mask_path=obj.ControlMaskFullPath,
        #                                                                search_dirs=search_paths)
        # self.create_image_viewmodel(source_key, source_permutations)
        #
        # target_key, target_permutations = self.load_image_into_manager(key=ViewType.Target.value,
        #                                                                image_path=obj.MappedImageFullPath,
        #                                                                mask_path=obj.MappedMaskFullPath,
        #                                                                search_dirs=search_paths)
        # self.create_image_viewmodel(target_key, target_permutations)

        with concurrent.futures.ThreadPoolExecutor() as pool:
            source_task = pool.submit(self.load_image_into_manager,
                                      key=ViewType.Source.value,
                                      image_path=obj.ControlImageFullPath,
                                      mask_path=obj.ControlMaskFullPath,
                                      search_dirs=search_paths)

            source_task.add_done_callback(
                lambda task: self.create_image_viewmodel(*task.result()))

            target_task = pool.submit(self.load_image_into_manager,
                                      key=ViewType.Target.value,
                                      image_path=obj.MappedImageFullPath,
                                      mask_path=obj.MappedMaskFullPath,
                                      search_dirs=search_paths)

            target_task.add_done_callback(
                lambda task: self.create_image_viewmodel(*task.result()))

        self._transform_controller.TransformModel = nornir_imageregistration.transforms.LoadTransform(obj.Transform)

    def load_image_into_manager(
            self,
            key: str | Enum | None,
            image_path: str,
            mask_path: str | None,
            search_dirs: list[str]) -> tuple[str, nornir_imageregistration.ImagePermutationHelper]:
        """Loads an image and optionally a mask from disk.
        :param key: The key to store the image under in the image manager. If None the key will be the base name of the image file.
        :return: A tuple with the key and the permutations object."""
        key = key if key is not None else os.path.basename(image_path)
        image_path = try_locate_file(image_path, search_dirs)
        image = nornir_imageregistration.LoadImage(image_path)
        image_mask = None
        if mask_path is not None:
            mask_path = try_locate_file(image_path, search_dirs)
            if mask_path is not None:
                image_mask = nornir_imageregistration.LoadImage(mask_path)

        permutations = self._image_manager.add(key=key,
                                               image=image,
                                               mask=image_mask)
        return key, permutations

    def create_image_viewmodel(self,
                               name: str | Enum,
                               permutations: nornir_imageregistration.ImagePermutationHelper) -> ImageViewModel:
        self._image_viewmodel_manager.add(name, permutations.Image)
