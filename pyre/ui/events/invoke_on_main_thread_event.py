from __future__ import annotations

from PyQt6.QtCore import QEvent
from dependency_injector.wiring import Provide
import traceback

import pyre
from pyre.container import IContainer
from pyre.interfaces import IEventManager

# from pyre.interfaces import IEventManager

class QtInvokeOnMainThreadEvent(QEvent):
    """A Qt event that invokes a callback on the main thread"""
    # Create a custom event type
    EVENT_TYPE = QEvent.Type(QEvent.Type.User + 1)

    _args: tuple | None
    _kwargs: dict | None
    _obj: IEventManager
    _stack_list: list[str] | None
    _stack: str | None

    _config = Provide[IContainer.config]

    @property
    def debug(self) -> bool:
        if "debug" not in self._config:
            return False

        return bool(self._config["debug"])

    @property
    def args(self) -> tuple | None:
        return self._args

    @property
    def kwargs(self) -> dict | None:
        return self._kwargs

    @property
    def obj(self) -> IEventManager | None:
        return self._obj

    def __init__(self, obj: IEventManager,
                 args: tuple | None = None,
                 kwargs: dict | None = None):
        super().__init__(QtInvokeOnMainThreadEvent.EVENT_TYPE)
        self._args = args
        self._kwargs = kwargs
        self._obj = obj
        self._stack_list = None
        self._stack = None

        if self.debug:
            _stack = traceback.format_stack()
            self._stack = '\n'.join(_stack)

    def invoke(self):
        """Invoke the callback for the event"""
        try:
            self._obj.invoke(*(self._args or ()), **(self._kwargs or {}))
        except Exception as e:
            if self.debug:
                print(f"Exception invoking event {e} from {self._stack}")

            raise
