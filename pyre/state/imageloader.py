import concurrent.futures
from enum import Enum
import logging
import os
import threading

from dependency_injector.wiring import inject, Provide
from pyre.settings import AppSettings

from nornir_imageregistration import StosFile
from nornir_imageregistration.core._core import RgbLikeToGrayscaleLuminance
import nornir_imageregistration
import nornir_imageregistration.transforms
from pyre.interfaces.managers import IImageManager, IImageViewModelManager, IImageLoader
from pyre.interfaces.named_tuples import ImageLoadResult, LoadStosResult
from pyre.resources import try_locate_file
from pyre.interfaces.viewtype import ViewType
from pyre.perf_debug import timed
from pyre.viewmodels import ImageViewModel
from pyre.controllers.transformcontroller import TransformController
from pyre.container import IContainer

logger = logging.getLogger(__name__)

FilepathCacheKey = tuple[str, str | None]


def make_filepath_cache_key(image_fullpath: str, mask_fullpath: str | None) -> FilepathCacheKey:
    """Return a normalized cache key for resolved image and mask paths."""
    return (
        os.path.normcase(image_fullpath),
        os.path.normcase(mask_fullpath) if mask_fullpath is not None else None,
    )


class ImageLoader(IImageLoader):
    """Loads images and creates viewmodels for them."""
    _transform_controller: TransformController
    _image_manager: IImageManager
    _image_viewmodel_manager: IImageViewModelManager
    _search_dirs: list[str] | None
    _replacement_paths: dict[str, str] | None
    _filepath_cache: dict[FilepathCacheKey, nornir_imageregistration.ImagePermutationHelper]
    _viewmodel_cache: dict[FilepathCacheKey, ImageViewModel]
    _cache_lock: threading.RLock

    @inject
    def __init__(self,
                 image_manager: IImageManager = Provide[IContainer.image_manager],
                 imageviewmodel_manager: IImageViewModelManager = Provide[IContainer.image_viewmodel_manager],
                 settings: AppSettings = Provide[IContainer.settings]):
        self._image_manager = image_manager
        self._image_viewmodel_manager = imageviewmodel_manager
        self._search_dirs = settings.ui.image_search_paths
        self._replacement_paths = settings.ui.replacement_paths
        self._filepath_cache = {}
        self._viewmodel_cache = {}
        self._cache_lock = threading.RLock()

    def load_stos_images(self, stos_path: str) -> LoadStosResult:
        """Decode STOS-linked images into the filepath cache (no viewmodels / no GL).

        Safe to call from a worker thread. Does not mutate the image or viewmodel managers.
        """
        with timed(f'load_stos_images {os.path.basename(stos_path)}'):
            obj = StosFile.Load(stos_path)

            search_paths = list(self._search_dirs) if self._search_dirs is not None else []
            search_paths.insert(0, os.path.dirname(stos_path))

            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                source_task = pool.submit(
                    self._load_image_cached,
                    key=ViewType.Source.value,
                    image_fullpath=obj.MappedImageFullPath,
                    mask_fullpath=obj.MappedMaskFullPath,
                    search_dirs=search_paths,
                    replacement_paths=self._replacement_paths,
                )
                target_task = pool.submit(
                    self._load_image_cached,
                    key=ViewType.Target.value,
                    image_fullpath=obj.ControlImageFullPath,
                    mask_fullpath=obj.ControlMaskFullPath,
                    search_dirs=search_paths,
                    replacement_paths=self._replacement_paths,
                )
                return LoadStosResult(
                    stos=obj,
                    source=source_task.result(),
                    target=target_task.result(),
                )

    def load_stos(self,
                  stos_path: str) -> LoadStosResult | None:
        """Load STOS images into the filepath cache and register them on the image manager.

        Does not create GL viewmodels; callers must invoke :meth:`create_image_viewmodel`
        on the main thread after this returns.
        """
        with timed(f'load_stos {os.path.basename(stos_path)}'):
            result = self.load_stos_images(stos_path)
            self.commit_load_results_to_image_manager(result)
            return result

    def commit_load_results_to_image_manager(self, result: LoadStosResult) -> None:
        """Register source/target permutations on the image manager (main thread)."""
        for load_result in (result.source, result.target):
            key = load_result.key
            if key in self._image_manager:  # type: ignore[operator]
                del self._image_manager[key]  # type: ignore[arg-type]
            self._image_manager.add(key=key, image=load_result.permutations)  # type: ignore[arg-type]

    def _load_image_cached(
            self,
            key: str | Enum | None,
            image_fullpath: str,
            mask_fullpath: str | None,
            search_dirs: list[str] | None = None,
            replacement_paths: dict[str, str] | None = None) -> ImageLoadResult:
        """Load image(+mask) into the filepath cache; do not touch image/viewmodel managers."""
        key = key if key is not None else os.path.basename(image_fullpath)
        found_image_fullpath = try_locate_file(image_fullpath, search_dirs or [], replacement_paths)  # type: ignore[arg-type]
        if found_image_fullpath is None:
            raise ValueError("Image file not found: " + image_fullpath + "\n\tin" + str(search_dirs))

        found_mask_fullpath: str | None = None
        if mask_fullpath is not None:
            found_mask_fullpath = try_locate_file(mask_fullpath, search_dirs or [], replacement_paths)  # type: ignore[arg-type]

        cache_key = make_filepath_cache_key(found_image_fullpath, found_mask_fullpath)

        img_color = False
        msk_color = False

        with self._cache_lock:
            cached = self._filepath_cache.get(cache_key)
        if cached is not None:
            permutations = cached
        else:
            with timed(f'LoadImage {os.path.basename(found_image_fullpath)}'):
                # Pyre display/tiling needs host arrays; avoid CuPy upload then .get() round-trip.
                image = nornir_imageregistration.LoadImage(found_image_fullpath, backend="numpy")
            image, img_color = RgbLikeToGrayscaleLuminance(image)
            if img_color:
                logger.warning(
                    "Image had color channels; converted to grayscale (luminance): %s",
                    found_image_fullpath,
                )

            image_mask = None
            if found_mask_fullpath is not None:
                with timed(f'LoadImage mask {os.path.basename(found_mask_fullpath)}'):
                    image_mask = nornir_imageregistration.LoadImage(found_mask_fullpath, backend="numpy")
                image_mask, msk_color = RgbLikeToGrayscaleLuminance(image_mask)
                if msk_color:
                    logger.warning(
                        "Mask had color channels; converted to grayscale (luminance): %s",
                        found_mask_fullpath,
                    )

            with timed(f'ImagePermutationHelper {os.path.basename(found_image_fullpath)}'):
                helper = nornir_imageregistration.ImagePermutationHelper(image, image_mask)
            with self._cache_lock:
                # Another worker may have filled the cache while we decoded.
                permutations = self._filepath_cache.setdefault(cache_key, helper)

        # Overlap extrema/stats with later viewmodel creation / GL upload.
        permutations.prefetch_extrema_async()

        return ImageLoadResult(key=str(key),
                               permutations=permutations,
                               image_fullpath=found_image_fullpath,
                               mask_fullpath=found_mask_fullpath,
                               image_original_fullpath=image_fullpath,
                               mask_original_fullpath=mask_fullpath,
                               image_converted_from_color=img_color,
                               mask_converted_from_color=msk_color,
                               filepath_cache_key=cache_key)

    def load_image_into_manager(
            self,
            key: str | Enum | None,
            image_fullpath: str,
            mask_fullpath: str | None,
            search_dirs: list[str] | None = None,
            replacement_paths: dict[str, str] | None = None) -> ImageLoadResult:
        """Loads an image and optionally a mask from disk into the image manager.
        :param key: The key to store the image under in the image manager. If None the key will be the base name of the image file.
        :return: A tuple with the key and the permutations object."""
        result = self._load_image_cached(
            key=key,
            image_fullpath=image_fullpath,
            mask_fullpath=mask_fullpath,
            search_dirs=search_dirs,
            replacement_paths=replacement_paths,
        )
        if result.key in self._image_manager:  # type: ignore[operator]
            del self._image_manager[result.key]  # type: ignore[arg-type]
        self._image_manager.add(key=result.key, image=result.permutations)  # type: ignore[arg-type]
        return result

    def _get_or_create_cached_viewmodel(self,
                                        cache_key: FilepathCacheKey,
                                        permutations: nornir_imageregistration.ImagePermutationHelper,
                                        image_fullpath: str) -> ImageViewModel:
        """Return a cached ImageViewModel for a filepath key, creating it on first use."""
        lock = getattr(self, "_cache_lock", None)
        if lock is None:
            self._cache_lock = threading.RLock()
            lock = self._cache_lock
        with lock:
            if not hasattr(self, "_viewmodel_cache") or self._viewmodel_cache is None:
                self._viewmodel_cache = {}
            cached = self._viewmodel_cache.get(cache_key)
            if cached is not None:
                return cached

            viewmodel = ImageViewModel(
                permutations.Image,
                image_filename=image_fullpath,
                managed_by_filepath_cache=True,
            )
            viewmodel.mark_managed_by_filepath_cache()
            self._viewmodel_cache[cache_key] = viewmodel
            return viewmodel

    def create_image_viewmodel(self,
                               name: str | Enum | None = None,
                               permutations: nornir_imageregistration.ImagePermutationHelper | None = None,
                               *,
                               load_result: ImageLoadResult | None = None) -> ImageViewModel:
        """Bind a viewmodel to a manager slot, reusing cached GL textures when the filepath matches."""
        if load_result is not None:
            name = load_result.key
            permutations = load_result.permutations
            cache_key = load_result.filepath_cache_key
            image_fullpath = load_result.image_fullpath
        else:
            cache_key = None
            image_fullpath = None

        if name is None or permutations is None:
            raise ValueError("create_image_viewmodel requires name and permutations or load_result")

        if cache_key is not None and image_fullpath is not None:
            viewmodel = self._get_or_create_cached_viewmodel(cache_key, permutations, image_fullpath)
            return self._image_viewmodel_manager.assign_slot(str(name), viewmodel)

        if name in self._image_viewmodel_manager:  # type: ignore[operator]
            del self._image_viewmodel_manager[name]  # type: ignore[index]
        return self._image_viewmodel_manager.add(str(name), permutations.Image)
