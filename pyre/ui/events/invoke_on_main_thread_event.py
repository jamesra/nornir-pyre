import wx
from dependency_injector.wiring import Provide
import traceback
from pyre.container import IContainer

# from pyre.interfaces import IEventManager

# An event that invokes a callback on the main thread
wx_INVOKE_ON_MAIN_THREAD_EventType = wx.NewEventType()
wx_EVT_INVOKE_ON_MAIN_THREAD = wx.PyEventBinder(wx_INVOKE_ON_MAIN_THREAD_EventType)


class wxInvokeOnMainThreadEvent(wx.PyEvent):
    _args: tuple | None
    _kwargs: dict | None
    _obj: "pyre.interfaces.IEventManager"
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
    def obj(self) -> "pyre.interfaces.IEventManager | None":
        return self._obj

    def __init__(self, obj: "pyre.interfaces.IEventManager",
                 args: tuple | None = None,
                 kwargs: dict | None = None):
        super().__init__(id=wx.ID_ANY, eventType=wx_INVOKE_ON_MAIN_THREAD_EventType)
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
            self._obj.invoke(*self._args, **self._kwargs)
        except Exception as e:
            if self.debug:
                print(f"Exception invoking event {e} from {self._stack}")

            raise
