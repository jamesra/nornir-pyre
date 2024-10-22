import threading
import abc
from pyre.command_interfaces import ICommand


class ICommandQueue(abc.ABC):

    @abc.abstractmethod
    def put(self, command: ICommand):
        raise NotImplementedError()

    @abc.abstractmethod
    def clear(self):
        raise NotImplementedError()

    @abc.abstractmethod
    def get(self) -> ICommand | None:
        raise NotImplementedError()

    @abc.abstractmethod
    def wait(self, timeout=None):
        raise NotImplementedError()

    @property
    @abc.abstractmethod
    def is_empty(self) -> bool:
        raise NotImplementedError()
