from dependency_injector import providers

from pyre import Space
from pyre.commands.callcontrolpointtomousecommand import CallControlPointToMouseCommand
from pyre.commands.togglecontrolpointselectioncommand import ToggleControlPointSelectionCommand
from pyre.interfaces.action import ControlPointAction
from pyre.interfaces.managers import IControlPointActionMap
from pyre.commands import DefaultTransformCommand
from pyre.commands.stos import ManipulateRigidTransformCommand, RegisterControlPointCommand, \
    TranslateControlPointCommand, DeleteControlPointCommand, \
    CreateControlPointCommand, CreateRegisterControlPointCommand, RefineRigidTransformCommand
from nornir_imageregistration.transforms.transform_type import TransformType
from pyre.commands.stos import GridTransformActionMap, TriangulationTransformActionMap
from pyre.observable import SetOperation


def _selection_command_providers() -> dict[ControlPointAction, providers.Provider]:
    return {
        ControlPointAction.REPLACE_SELECTION: providers.Factory(
            ToggleControlPointSelectionCommand, set_operation=SetOperation.Replace
        ).provider,
        ControlPointAction.APPEND_SELECTION: providers.Factory(
            ToggleControlPointSelectionCommand, set_operation=SetOperation.Union
        ).provider,
        ControlPointAction.TOGGLE_SELECTION: providers.Factory(
            ToggleControlPointSelectionCommand, set_operation=SetOperation.SymmetricDifference
        ).provider,
    }


def _register_command_providers() -> dict[ControlPointAction, providers.Provider]:
    return {
        ControlPointAction.REGISTER: providers.Factory(
            RegisterControlPointCommand, source_image=Space.Source, target_image=Space.Target
        ).provider,
        ControlPointAction.REGISTER_ALL: providers.Factory(
            RegisterControlPointCommand,
            source_image=Space.Source,
            target_image=Space.Target,
            register_all=True,
        ).provider,
    }


def _mesh_like_command_providers() -> dict[ControlPointAction, providers.Provider]:
    return {
        ControlPointAction.NONE: providers.Factory(DefaultTransformCommand).provider,
        ControlPointAction.TRANSLATE: providers.Factory(TranslateControlPointCommand).provider,
        ControlPointAction.TRANSLATE_ALL: providers.Factory(
            TranslateControlPointCommand, translate_all=True
        ).provider,
        ControlPointAction.DELETE: providers.Factory(DeleteControlPointCommand).provider,
        **_selection_command_providers(),
        **_register_command_providers(),
        ControlPointAction.CREATE: providers.Factory(CreateControlPointCommand).provider,
        ControlPointAction.CREATE_REGISTER: providers.Factory(
            CreateRegisterControlPointCommand, source_image=Space.Source, target_image=Space.Target
        ).provider,
        ControlPointAction.CALL_TO_MOUSE: providers.Factory(CallControlPointToMouseCommand).provider,
    }


"""Maps a transform type to a dictionary that maps the transform type to commands. 
   ControlPointAction.None is the default command."""
action_command_dp_map = providers.Dict({
    TransformType.GRID: providers.Dict({
        ControlPointAction.NONE: providers.Factory(DefaultTransformCommand).provider,
        ControlPointAction.TRANSLATE: providers.Factory(TranslateControlPointCommand).provider,
        ControlPointAction.TRANSLATE_ALL: providers.Factory(TranslateControlPointCommand, translate_all=True).provider,
        **_selection_command_providers(),
        **_register_command_providers(),
        ControlPointAction.CALL_TO_MOUSE: providers.Factory(CallControlPointToMouseCommand).provider

        # ControlPointAction.DELETE: providers.Factory(DeleteControlPointCommand), Grid transform does not support DELETE
    }),
    TransformType.MESH: providers.Dict(_mesh_like_command_providers()),
    TransformType.RBF: providers.Dict(_mesh_like_command_providers()),
    TransformType.RIGID: providers.Dict({
        ControlPointAction.NONE: providers.Factory(DefaultTransformCommand).provider,
        ControlPointAction.TRANSLATE: providers.Factory(ManipulateRigidTransformCommand).provider,
        ControlPointAction.REFINE_RIGID_ANGLE: providers.Factory(
            RefineRigidTransformCommand, refine_scale=False).provider,
        ControlPointAction.REFINE_RIGID_ANGLE_SCALE: providers.Factory(
            RefineRigidTransformCommand, refine_scale=True).provider,
        # ControlPointAction.DELETE: providers.Factory(DeleteControlPointCommand), RIGID Does not support DELETE
    })
})

# This map determines which actions can be taken for a mouse position given the current transform type
# transform_control_point_action_maps: providers.Aggregate[providers.Factory[IControlPointActionMap]] = \
#     providers.Aggregate({
#         TransformType.GRID: providers.Factory(GridTransformActionMap),
#         TransformType.MESH: providers.Factory(TriangulationTransformActionMap),
#         TransformType.RBF: providers.Factory(TriangulationTransformActionMap),
#         TransformType.RIGID: providers.Factory(TriangulationTransformActionMap),
#     })
