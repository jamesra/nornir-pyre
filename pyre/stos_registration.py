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


def sync_stos_registration_roles(
        stos_state: object,
        warped: nornir_imageregistration.ImagePermutationHelper,
        fixed: nornir_imageregistration.ImagePermutationHelper,
) -> None:
    """Record resolved registration roles on ``StosState``."""
    if not hasattr(stos_state, "_fixed_image_permutations"):
        return
    stos_state._warped_image_permutations = warped  # type: ignore[attr-defined]
    stos_state._fixed_image_permutations = fixed  # type: ignore[attr-defined]


def wire_stos_state_after_load(
        stos_state: object,
        image_viewmodel_manager: object,
) -> None:
    """Point StosState viewmodels at the slots populated by ``ImageLoader.load_stos``."""
    from pyre.interfaces.viewtype import ViewType

    if not hasattr(stos_state, "FixedImageViewModel"):
        return

    fixed_vm = None
    warped_vm = None
    try:
        fixed_vm = image_viewmodel_manager[ViewType.Target.value]
    except (KeyError, TypeError):
        pass
    try:
        warped_vm = image_viewmodel_manager[ViewType.Source.value]
    except (KeyError, TypeError):
        pass

    stos_state.FixedImageViewModel = fixed_vm  # type: ignore[attr-defined]
    stos_state.WarpedImageViewModel = warped_vm  # type: ignore[attr-defined]

    update_permutations = getattr(stos_state, "_update_image_permutations", None)
    if callable(update_permutations):
        fixed_mask = getattr(stos_state, "FixedImageMaskViewModel", None)
        warped_mask = getattr(stos_state, "WarpedImageMaskViewModel", None)
        stos_state._fixed_image_permutations = update_permutations(fixed_vm, fixed_mask)  # type: ignore[attr-defined]
        stos_state._warped_image_permutations = update_permutations(warped_vm, warped_mask)  # type: ignore[attr-defined]


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
