from dependency_injector.wiring import Provide, inject
import logging
import threading
from pyre.command_interfaces import ICommand
from pyre.interfaces.managers.command_queue import ICommandQueue
from pyre.container import IContainer


class CommandQueue(ICommandQueue):
    _queue: list[ICommand]
    _lock: threading.Lock
    _event: threading.Event
    _logger: logging.Logger

    @inject
    def __init__(self):
        self._queue = []
        self._lock = threading.Lock()
        self.event = threading.Event()

    def put(self, command: ICommand):
        with self._lock:
            self._queue.append(command)
            logging.info(f'CommandQueue.put {command}')
            self.event.set()

    def clear(self):
        with self._lock:
            self._queue.clear()
            logging.info(f'CommandQueue.clear()')
            self.event.clear()

    def get(self) -> ICommand | None:
        with self._lock:
            if len(self._queue) == 0:
                self.event.clear()
                logging.info(f'CommandQueue.get: No commands in queue')
                return None

            value = self._queue.pop(0)
            logging.info(f'CommandQueue.get -> {value}')
            return value

    def wait(self, timeout=None):
        self.event.wait(timeout)

    @property
    def is_empty(self) -> bool:
        with self._lock:
            return len(self._queue) == 0
