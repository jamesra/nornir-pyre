import concurrent.futures
from enum import Enum
import os

from dependency_injector.wiring import inject, Provide
from pyre.settings import AppSettings

from nornir_imageregistration import StosFile
import nornir_imageregistration.transforms
from pyre.interfaces.managers import IImageManager, IImageViewModelManager, IImageLoader
from pyre.interfaces.named_tuples import ImageLoadResult, LoadStosResult
from pyre.resources import try_locate_file
from pyre.interfaces.viewtype import ViewType
from pyre.viewmodels import ImageViewModel
from pyre.controllers.transformcontroller import TransformController
from pyre.container import IContainer


class ImageLoader(IImageLoader):
    """Loads images and creates viewmodels for them."""
    _transform_controller: TransformController
    _image_manager: IImageManager
    _image_viewmodel_manager: IImageViewModelManager
    _search_dirs: list[str] | None
    _replacement_paths: dict[str, str] | None

    @inject
    def __init__(self,
                 image_manager: IImageManager = Provide[IContainer.image_manager],
                 imageviewmodel_manager: IImageViewModelManager = Provide[IContainer.imageviewmodel_manager],
                 settings: AppSettings = Provide[IContainer.settings]):
        self._image_manager = image_manager
        self._image_viewmodel_manager = imageviewmodel_manager
        self._search_dirs = settings.ui.image_search_paths
        self._replacement_paths = settings.ui.replacement_paths

    def load_stos(self,
                  stos_path: str) -> LoadStosResult | None:
        """Loads a stos file, images are loaded into the image manager and the transform is returned"""
        obj = StosFile.Load(stos_path)

        search_paths = list(self._search_dirs) if self._search_dirs is not None else []
        search_paths.insert(0, os.path.dirname(stos_path))

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
                                      image_fullpath=obj.MappedImageFullPath,
                                      mask_fullpath=obj.MappedMaskFullPath,
                                      search_dirs=search_paths,
                                      replacement_paths=self._replacement_paths)

            source_task.add_done_callback(
                lambda task: self.create_image_viewmodel(name=task.result().key,
                                                         permutations=task.result().permutations))

            target_task = pool.submit(self.load_image_into_manager,
                                      key=ViewType.Target.value,
                                      image_fullpath=obj.ControlImageFullPath,
                                      mask_fullpath=obj.ControlMaskFullPath,
                                      search_dirs=search_paths,
                                      replacement_paths=self._replacement_paths)
            target_task.add_done_callback(
                lambda task: self.create_image_viewmodel(name=task.result().key,
                                                         permutations=task.result().permutations))

            result = LoadStosResult(stos=obj,
                                    source=source_task.result(),
                                    target=target_task.result())
            return result

    def load_image_into_manager(
            self,
            key: str | Enum | None,
            image_fullpath: str,
            mask_fullpath: str | None,
            search_dirs: list[str] | None = None,
            replacement_paths: dict[str, str] | None = None) -> ImageLoadResult:
        """Loads an image and optionally a mask from disk.
        :param key: The key to store the image under in the image manager. If None the key will be the base name of the image file.
        :return: A tuple with the key and the permutations object."""
        key = key if key is not None else os.path.basename(image_fullpath)
        found_image_fullpath = try_locate_file(image_fullpath, search_dirs, replacement_paths)
        if found_image_fullpath is None:
            raise ValueError("Image file not found: " + image_fullpath + "\n\tin" + str(search_dirs))

        image = nornir_imageregistration.LoadImage(found_image_fullpath)
        image_mask = None
        found_mask_fullpath = None
        if mask_fullpath is not None:
            found_mask_fullpath = try_locate_file(mask_fullpath, search_dirs, replacement_paths)
            if found_mask_fullpath is not None:
                image_mask = nornir_imageregistration.LoadImage(found_mask_fullpath)

        if key in self._image_manager:
            del self._image_manager[key]

        permutations = self._image_manager.add(key=key,
                                               image=image,
                                               mask=image_mask)
        return ImageLoadResult(key=key,
                               permutations=permutations,
                               image_fullpath=found_image_fullpath,
                               mask_fullpath=found_mask_fullpath,
                               image_original_fullpath=image_fullpath,
                               mask_original_fullpath=mask_fullpath)

    def create_image_viewmodel(self,
                               name: str | Enum,
                               permutations: nornir_imageregistration.ImagePermutationHelper) -> ImageViewModel:
        if name in self._image_viewmodel_manager:
            del self._image_viewmodel_manager[name]
        return self._image_viewmodel_manager.add(name, permutations.Image)
