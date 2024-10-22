from dependency_injector import providers, containers
from dependency_injector.providers import Factory, Dict
import pyre.commands
from pyre.interfaces.action import ControlPointAction
from pyre.command_interfaces import ICommand

#
# class ControlPointCommandContainer(containers.DeclarativeContainer):
#     """Container for control point commands"""
#
#     stos_command_map = providers.Dict({
#         ControlPointAction.NONE: providers.Factory(pyre.commands.DefaultTransformCommand),
#         # ControlPointAction.CREATE: providers.Factory(pyre.commands.DefaultStosTransformCommand),
#         # ControlPointAction.DELETE: providers.Factory(pyre.commands.DeleteControlPointCommand),
#         ControlPointAction.TRANSLATE: providers.Factory(pyre.commands.stos.TranslateControlPointCommand),
#         # ControlPointAction.REGISTER: providers.Factory(pyre.commands.RegisterControlPointCommand)
#     })
