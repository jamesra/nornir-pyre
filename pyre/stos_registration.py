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

    if stos_filename and os.path.isfile(stos_filename):
        stos = StosFile.Load(stos_filename)
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
