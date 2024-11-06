from dependency_injector import providers

from pyre.commands.togglecontrolpointselectioncommand import ToggleControlPointSelectionCommand
from pyre.interfaces.action import ControlPointAction
from pyre.interfaces.managers import IControlPointActionMap
from pyre.commands import DefaultTransformCommand
from pyre.commands.stos import TranslateControlPointCommand, DeleteControlPointCommand, CreateControlPointCommand
from nornir_imageregistration.transforms.transform_type import TransformType
from pyre.commands.stos import GridTransformActionMap, TriangulationTransformActionMap
from pyre.observable import SetOperation

"""Maps a transform type to a dictionary that maps the transform type to commands. 
   ControlPointAction.None is the default command."""
action_command_dp_map = providers.Dict({
    TransformType.GRID: providers.Dict({
        ControlPointAction.NONE: providers.Factory(DefaultTransformCommand).provider,
        ControlPointAction.TRANSLATE: providers.Factory(TranslateControlPointCommand).provider,
        ControlPointAction.REPLACE_SELECTION: providers.Factory(ToggleControlPointSelectionCommand,
                                                                set_operation=SetOperation.Replace).provider,
        ControlPointAction.APPEND_SELECTION: providers.Factory(ToggleControlPointSelectionCommand,
                                                               set_operation=SetOperation.Union).provider,
        ControlPointAction.TOGGLE_SELECTION: providers.Factory(ToggleControlPointSelectionCommand,
                                                               set_operation=SetOperation.SymmetricDifference).provider,
        # ControlPointAction.DELETE: providers.Factory(DeleteControlPointCommand), Grid transform does not support DELETE
    }),
    TransformType.MESH: providers.Dict({
        ControlPointAction.NONE: providers.Factory(DefaultTransformCommand).provider,
        ControlPointAction.TRANSLATE: providers.Factory(TranslateControlPointCommand).provider,
        ControlPointAction.DELETE: providers.Factory(DeleteControlPointCommand).provider,
        ControlPointAction.REPLACE_SELECTION: providers.Factory(ToggleControlPointSelectionCommand,
                                                                set_operation=SetOperation.Replace).provider,
        ControlPointAction.APPEND_SELECTION: providers.Factory(ToggleControlPointSelectionCommand,
                                                               set_operation=SetOperation.Union).provider,
        ControlPointAction.TOGGLE_SELECTION: providers.Factory(ToggleControlPointSelectionCommand,
                                                               set_operation=SetOperation.SymmetricDifference).provider,
    }),
    TransformType.RBF: providers.Dict({
        ControlPointAction.NONE: providers.Factory(DefaultTransformCommand).provider,
        ControlPointAction.TRANSLATE: providers.Factory(TranslateControlPointCommand).provider,
        ControlPointAction.DELETE: providers.Factory(DeleteControlPointCommand).provider,
        ControlPointAction.REPLACE_SELECTION: providers.Factory(ToggleControlPointSelectionCommand,
                                                                set_operation=SetOperation.Replace).provider,
        ControlPointAction.APPEND_SELECTION: providers.Factory(ToggleControlPointSelectionCommand,
                                                               set_operation=SetOperation.Union).provider,
        ControlPointAction.TOGGLE_SELECTION: providers.Factory(ToggleControlPointSelectionCommand,
                                                               set_operation=SetOperation.SymmetricDifference).provider,
    }),
    TransformType.RIGID: providers.Dict({
        ControlPointAction.NONE: providers.Factory(DefaultTransformCommand).provider,
        ControlPointAction.TRANSLATE: providers.Factory(TranslateControlPointCommand).provider,
        # ControlPointAction.DELETE: providers.Factory(DeleteControlPointCommand), RIGID Does not support DELETE
    })
})

action_command_map = {
    TransformType.GRID: {
        ControlPointAction.NONE: DefaultTransformCommand,
        ControlPointAction.TRANSLATE: TranslateControlPointCommand
    },
    TransformType.MESH: {
        ControlPointAction.NONE: DefaultTransformCommand,
        ControlPointAction.TRANSLATE: TranslateControlPointCommand,
        ControlPointAction.DELETE: DeleteControlPointCommand,
        ControlPointAction.CREATE: CreateControlPointCommand,
    },
    TransformType.RBF: {
        ControlPointAction.NONE: DefaultTransformCommand,
        ControlPointAction.TRANSLATE: TranslateControlPointCommand,
        ControlPointAction.DELETE: DeleteControlPointCommand,
        ControlPointAction.CREATE: CreateControlPointCommand,
    },
    TransformType.RIGID: {
        ControlPointAction.NONE: DefaultTransformCommand,
        ControlPointAction.TRANSLATE: TranslateControlPointCommand,
    }
}

# This map determines which actions can be taken for a mouse position given the current transform type
# transfom_control_point_action_maps: providers.Aggregate[providers.Factory[IControlPointActionMap]] = \
#     providers.Aggregate({
#         TransformType.GRID: providers.Factory(GridTransformActionMap),
#         TransformType.MESH: providers.Factory(TriangulationTransformActionMap),
#         TransformType.RBF: providers.Factory(TriangulationTransformActionMap),
#         TransformType.RIGID: providers.Factory(TriangulationTransformActionMap),
#     })
