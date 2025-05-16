from __future__ import annotations
from . import ObservedAction
from typing import Sequence, TypeVar, Generic, Callable, Iterable

T = TypeVar('T')

"""The observer function signature.  It does its best to notify which action was taken and which indicies were affected if relevant"""
ListObserverCallable = Callable[['ObservableList[T]', ObservedAction, Iterable[int] | None], None]


class ObservableList(list, Generic[T]):
    """A python list that notifies observers when it is modified"""
    _call_wrapper: Callable = None

    def __init__(self, initial_list: Sequence[T] | None = None, call_wrapper: Callable = None):
        """
                :param initial_list: Populates the list with initial values
                :param call_wrapper: Used when we can notification callbacks to go through an event loop such as wx.CallAfter, can also be used to launch callbacks on a thread
                """
        super().__init__(initial_list if initial_list is not None else [])
        self._observers: list[ListObserverCallable[T]] = []

    def add_observer(self, observer: ListObserverCallable[T]):
        self._observers.append(observer)

    def remove_observer(self, observer: ListObserverCallable[T]):
        self._observers.remove(observer)

    def _notify_observers(self, action: ObservedAction, items: list[int] | None = None):
        for observer in self._observers:
            if self._call_wrapper is not None:
                self._call_wrapper(observer, self, action, items)
            else:
                observer(self, action, items)

    def append(self, item: T):
        super().append(item)
        self._notify_observers(ObservedAction.ADD, [len(self) - 1])

    def remove(self, item: T):
        i = self.index(item)
        super().pop(i)
        self._notify_observers(ObservedAction.REMOVE, [i])

    def __setitem__(self, index: int, value: T):
        super().__setitem__(index, value)
        self._notify_observers(ObservedAction.UPDATE, [index])

    def __delitem__(self, index: int):
        super().__delitem__(index)
        self._notify_observers(ObservedAction.REMOVE, [index])

    def extend(self, iterable: Sequence[T]):
        super().extend(iterable)
        self._notify_observers(ObservedAction.ADD, list(range(len(self) - len(iterable), len(self))))

    def insert(self, index: int, item: T):
        super().insert(index, item)
        self._notify_observers(ObservedAction.INSERT, [index])

    def pop(self, index: int = -1) -> T:
        item = super().pop(index)
        self._notify_observers(ObservedAction.REMOVE, [index])
        return item

    def clear(self):
        super().clear()
        self._notify_observers(ObservedAction.CLEAR)
