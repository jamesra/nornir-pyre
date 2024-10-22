from dependency_injector import providers, containers
from dependency_injector.providers import Factory, Dict
from pyre.command_interfaces import ICommand
from pyre.interfaces.action import ControlPointAction
from pyre.commands import DefaultTransformCommand
from pyre.commands.stos import TranslateControlPointCommand, DeleteControlPointCommand, CreateControlPointCommand
from nornir_imageregistration.transforms.transform_type import TransformType
from pyre.container import ControlPointActionCommandMapType

"""Maps a transform type to a dictionary that maps the transform type to commands. 
   ControlPointAction.None is the default command."""
action_command_dp_map = providers.Dict[TransformType, ControlPointActionCommandMapType]({
    TransformType.GRID: providers.Dict({
        ControlPointAction.NONE: providers.Factory(DefaultTransformCommand),
        ControlPointAction.TRANSLATE: providers.Factory(TranslateControlPointCommand),
        # ControlPointAction.DELETE: providers.Factory(DeleteControlPointCommand), Grid transform does not support DELETE
    }),
    TransformType.MESH: providers.Dict({
        ControlPointAction.NONE: providers.Factory(DefaultTransformCommand),
        ControlPointAction.TRANSLATE: providers.Factory(TranslateControlPointCommand),
        ControlPointAction.DELETE: providers.Factory(DeleteControlPointCommand),
    }),
    TransformType.RBF: providers.Dict({
        ControlPointAction.NONE: providers.Factory(DefaultTransformCommand),
        ControlPointAction.TRANSLATE: providers.Factory(TranslateControlPointCommand),
        ControlPointAction.DELETE: providers.Factory(DeleteControlPointCommand),
    }),
    TransformType.RIGID: providers.Dict({
        ControlPointAction.NONE: providers.Factory(DefaultTransformCommand),
        ControlPointAction.TRANSLATE: providers.Factory(TranslateControlPointCommand),
        # ControlPointAction.DELETE: providers.Factory(DeleteControlPointCommand), RIGID Does not support DELETE
    })
})

action_command_map = {
    TransformType.GRID: {
        ControlPointAction.NONE: DefaultTransformCommand,
        ControlPointAction.TRANSLATE: TranslateControlPointCommand,
        # ControlPointAction.DELETE: DeleteControlPointCommand, transform does not support DELETE
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
        # ControlPointAction.DELETE: DeleteControlPointCommand, transform does not support DELETE
    }
}
