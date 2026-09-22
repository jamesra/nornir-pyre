"""STOS registration helpers without Qt dependencies."""

from __future__ import annotations

import os
from typing import Protocol, runtime_checkable

import nornir_imageregistration
from nornir_imageregistration.files.stosfile import StosFile

@runtime_checkable
class ImageManagerLike(Protocol):
    """Minimal image-manager mapping used for registration orientation."""

    def __getitem__(self, key: str) -> nornir_imageregistration.ImagePermutationHelper:
        ...

    def __contains__(self, key: str) -> bool:
        ...


def _basename_casefold(path: str | None) -> str | None:
    """Return a case-insensitive basename for path comparison, or None."""
    if path is None:
        return None
    return os.path.basename(path).casefold()


def resolve_warped_and_fixed_image_data(
        image_manager: ImageManagerLike,
        source_image_key: str,
        target_image_key: str,
        stos_filename: str | None = None,
        stos: StosFile | None = None,
        settings_source_image_path: str | None = None,
        settings_target_image_path: str | None = None,
) -> tuple[nornir_imageregistration.ImagePermutationHelper,
           nornir_imageregistration.ImagePermutationHelper]:
    """Return (warped, fixed) image helpers for nornir slice-to-slice registration.

    Slice registration maps the moving section (mapped / lower toward center) into the
    target section (control). When a STOS file is available, use its mapped and control
    image paths to locate the correct slots in the image manager.

    Otherwise assume Pyre's Source slot is the moving image and Target is the fixed image
    (same layout as ``load_stos``: mapped→Source, control→Target).
    """
    slot_for_source = image_manager[source_image_key]
    slot_for_target = image_manager[target_image_key]

    if stos is None and stos_filename and os.path.isfile(stos_filename):
        stos = StosFile.Load(stos_filename)

    if stos is not None:
        mapped_bn = _basename_casefold(stos.MappedImageFullPath)
        control_bn = _basename_casefold(stos.ControlImageFullPath)
        source_bn = _basename_casefold(settings_source_image_path)
        target_bn = _basename_casefold(settings_target_image_path)

        warped_slot: nornir_imageregistration.ImagePermutationHelper | None = None
        fixed_slot: nornir_imageregistration.ImagePermutationHelper | None = None

        if source_bn == mapped_bn:
            warped_slot = slot_for_source
        elif target_bn == mapped_bn:
            warped_slot = slot_for_target

        if source_bn == control_bn:
            fixed_slot = slot_for_source
        elif target_bn == control_bn:
            fixed_slot = slot_for_target

        if warped_slot is not None and fixed_slot is not None:
            return warped_slot, fixed_slot

    return slot_for_source, slot_for_target


resolve_source_and_target_image_data = resolve_warped_and_fixed_image_data


def try_resolve_warped_and_fixed_image_data(
        image_manager: ImageManagerLike,
        source_image_key: str,
        target_image_key: str,
        stos_filename: str | None = None,
        stos: StosFile | None = None,
        settings_source_image_path: str | None = None,
        settings_target_image_path: str | None = None,
) -> tuple[nornir_imageregistration.ImagePermutationHelper,
           nornir_imageregistration.ImagePermutationHelper] | None:
    """Like ``resolve_warped_and_fixed_image_data`` but returns None when either slot is unloaded."""
    if source_image_key not in image_manager or target_image_key not in image_manager:
        return None
    return resolve_warped_and_fixed_image_data(
        image_manager,
        source_image_key,
        target_image_key,
        stos_filename=stos_filename,
        stos=stos,
        settings_source_image_path=settings_source_image_path,
        settings_target_image_path=settings_target_image_path,
    )


try_resolve_source_and_target_image_data = try_resolve_warped_and_fixed_image_data


def sync_stos_registration_roles(
        stos_state: object,
        warped: nornir_imageregistration.ImagePermutationHelper,
        fixed: nornir_imageregistration.ImagePermutationHelper,
) -> None:
    """Record resolved registration roles on ``StosState`` and republish shm images.

    The internal attribute naming follows the LoadSourceImage / LoadTargetImage
    convention, where ``_fixed_image_permutations`` holds the Pyre *Source* slot
    (STOS mapped/warped section) and ``_warped_image_permutations`` holds the
    Pyre *Target* slot (STOS control/fixed section).  The *warped* and *fixed*
    parameters use nornir registration semantics (warped = mapped, fixed = control).
    """
    if not hasattr(stos_state, "_fixed_image_permutations"):
        return
    stos_state._fixed_image_permutations = warped   # type: ignore[attr-defined]
    stos_state._warped_image_permutations = fixed    # type: ignore[attr-defined]
    _publish_alignment_images(stos_state)


def _publish_alignment_images(stos_state: object) -> None:
    """Republish both sides' alignment images when the helpers were replaced."""
    publish = getattr(stos_state, "publish_alignment_images", None)
    if callable(publish):
        publish()


def wire_stos_state_after_load(
        stos_state: object,
        image_viewmodel_manager: object,
        image_manager: object | None = None,
) -> None:
    """Point StosState viewmodels at the slots populated by ``ImageLoader.load_stos``.

    When mask view-models are unset (typical after STOS open), keep Mask arrays
    already present on the ImageManager slots instead of rebuilding permutations
    with ``mask=None`` and dropping the STOS masks.
    """
    from pyre.interfaces.viewtype import ViewType

    if not hasattr(stos_state, "SourceImageViewModel") and not hasattr(stos_state, "FixedImageViewModel"):
        return

    source_vm = None
    target_vm = None
    try:
        source_vm = image_viewmodel_manager[ViewType.Source.value]
    except (KeyError, TypeError):
        pass
    try:
        target_vm = image_viewmodel_manager[ViewType.Target.value]
    except (KeyError, TypeError):
        pass

    stos_state.SourceImageViewModel = source_vm  # type: ignore[attr-defined]
    stos_state.TargetImageViewModel = target_vm  # type: ignore[attr-defined]

    source_mask_vm = getattr(stos_state, "FixedImageMaskViewModel", None)
    target_mask_vm = getattr(stos_state, "WarpedImageMaskViewModel", None)

    source_slot = None
    target_slot = None
    if image_manager is not None:
        try:
            source_slot = image_manager[ViewType.Source.value]  # type: ignore[index]
        except (KeyError, TypeError):
            pass
        try:
            target_slot = image_manager[ViewType.Target.value]  # type: ignore[index]
        except (KeyError, TypeError):
            pass

    update_permutations = getattr(stos_state, "_update_image_permutations", None)
    if callable(update_permutations):
        if source_mask_vm is not None:
            stos_state._fixed_image_permutations = update_permutations(source_vm, source_mask_vm)  # type: ignore[attr-defined]
        elif source_slot is not None:
            # Preserve STOS-loaded Mask from the image manager.
            stos_state._fixed_image_permutations = source_slot  # type: ignore[attr-defined]
        else:
            stos_state._fixed_image_permutations = update_permutations(source_vm, None)  # type: ignore[attr-defined]

        if target_mask_vm is not None:
            stos_state._warped_image_permutations = update_permutations(target_vm, target_mask_vm)  # type: ignore[attr-defined]
        elif target_slot is not None:
            stos_state._warped_image_permutations = target_slot  # type: ignore[attr-defined]
        else:
            stos_state._warped_image_permutations = update_permutations(target_vm, None)  # type: ignore[attr-defined]

        _publish_alignment_images(stos_state)

    # #region agent log
    try:
        import json
        import time
        fixed_perm = getattr(stos_state, "_fixed_image_permutations", None)
        warped_perm = getattr(stos_state, "_warped_image_permutations", None)
        with open(r"d:\src\git\nornir\debug-79a4da.log", "a", encoding="utf-8") as _f:
            _f.write(json.dumps({
                "sessionId": "79a4da",
                "hypothesisId": "G,I",
                "location": "stos_registration.py:wire_stos_state_after_load",
                "message": "wired stos masks after load",
                "data": {
                    "mask_vm_fixed_is_none": source_mask_vm is None,
                    "mask_vm_warped_is_none": target_mask_vm is None,
                    "fixed_perm_mask_is_none": fixed_perm is None or getattr(fixed_perm, "Mask", None) is None,
                    "warped_perm_mask_is_none": warped_perm is None or getattr(warped_perm, "Mask", None) is None,
                    "used_image_manager": image_manager is not None,
                    "runId": "post-fix",
                },
                "timestamp": int(time.time() * 1000),
            }) + "\n")
    except Exception:
        pass
    # #endregion


def ensure_mask_viewmodels_from_load(
        stos_state: object,
        load_result: object,
) -> None:
    """Populate Fixed/Warped mask view-models from a STOS load when unset.

    STOS open loads masks into ImagePermutationHelper but historically left
    MaskViewModels None, so Clear-masked-points and other VM-only paths looked
    like masks were missing.
    """
    from pyre.viewmodels import ImageViewModel

    source = getattr(load_result, "source", None)
    target = getattr(load_result, "target", None)

    if (
        getattr(stos_state, "FixedImageMaskViewModel", None) is None
        and source is not None
        and getattr(source, "permutations", None) is not None
        and source.permutations.Mask is not None
    ):
        stos_state.FixedImageMaskViewModel = ImageViewModel(  # type: ignore[attr-defined]
            source.permutations.Mask,
            image_filename=getattr(source, "mask_fullpath", None),
        )

    if (
        getattr(stos_state, "WarpedImageMaskViewModel", None) is None
        and target is not None
        and getattr(target, "permutations", None) is not None
        and target.permutations.Mask is not None
    ):
        stos_state.WarpedImageMaskViewModel = ImageViewModel(  # type: ignore[attr-defined]
            target.permutations.Mask,
            image_filename=getattr(target, "mask_fullpath", None),
        )


def apply_stos_transform_to_controller(
        transform_controller: object,
        transform_string: str,
) -> nornir_imageregistration.ITransform:
    """Parse a STOS transform string and install it on the shared TransformController."""
    transform = nornir_imageregistration.transforms.LoadTransform(transform_string)
    transform_controller.TransformModel = transform  # type: ignore[attr-defined]
    return transform_controller.TransformModel  # type: ignore[attr-defined,no-any-return]


def normalize_rigid_transform_for_pyre_editing(
        transform: nornir_imageregistration.ITransform,
) -> nornir_imageregistration.ITransform:
    """Upgrade legacy rigid models to CenteredSimilarity2D for Pyre interactive scale."""
    if isinstance(transform, (
            nornir_imageregistration.transforms.RigidTranslation,
            nornir_imageregistration.transforms.Rigid,
    )) and not isinstance(
            transform, nornir_imageregistration.transforms.CenteredSimilarity2DTransform):
        return nornir_imageregistration.transforms.ConvertRigidTransformToCenteredSimilarityTransform(
            transform)
    return transform
