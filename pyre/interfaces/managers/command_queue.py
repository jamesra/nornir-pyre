import threading
import abc
from pyre.command_interfaces import ICommand, IInstantCommand


class ICommandQueue(abc.ABC):

    @abc.abstractmethod
    def put(self, command: IInstantCommand):
        raise NotImplementedError()

    @abc.abstractmethod
    def clear(self):
        raise NotImplementedError()

    @abc.abstractmethod
    def get(self) -> IInstantCommand | None:
        raise NotImplementedError()

    @abc.abstractmethod
    def wait(self, timeout=None):
        raise NotImplementedError()

    @property
    @abc.abstractmethod
    def is_empty(self) -> bool:
        raise NotImplementedError()
