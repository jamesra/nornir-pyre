from typing import Iterable, TypeVar, Generic, Callable, AbstractSet

from dependency_injector.providers import AbstractSingleton

from . import ObservedAction

T = TypeVar('T')

# The set observer function signature.  It reports which objects were added or removed.  No other actions are possible in sets
SetObserverCallable = Callable[['ObservableSet[T]', ObservedAction, AbstractSet[T] | None], None]


class ObservableSet(set, Generic[T]):
    """A python set that notifies observers when it is modified"""

    def __init__(self, initial_set: Iterable[T] | None = None):
        super().__init__(initial_set if initial_set is not None else [])
        self._observers: list[SetObserverCallable[T]] = []

    def add_observer(self, observer: SetObserverCallable[T]):
        self._observers.append(observer)

    def remove_observer(self, observer: SetObserverCallable[T]):
        self._observers.remove(observer)

    def _notify_observers(self, action: ObservedAction, items: AbstractSet[T] | None = None):
        for observer in self._observers:
            observer(self, action, items)

    def add(self, item: T):
        """Add element elem to the set."""
        super().add(item)
        self._notify_observers(ObservedAction.ADD, frozenset([item]))

    def remove(self, item: T):
        """Remove element elem from the set. Raises KeyError if elem is not contained in the set."""
        super().remove(item)
        self._notify_observers(ObservedAction.REMOVE, frozenset([item]))

    def discard(self, item: T):
        """Remove element elem from the set if it is present."""
        if item in self:
            super().discard(item)
            self._notify_observers(ObservedAction.REMOVE, frozenset([item]))

    def clear(self):
        """Remove all elements from the set."""
        super().clear()
        self._notify_observers(ObservedAction.CLEAR)

    def update(self, *others: Iterable[T]):
        """Update the set, adding elements from all others."""
        intersection = frozenset(*others) - self
        super().update(*others)
        self._notify_observers(ObservedAction.ADD, intersection)

    def intersection_update(self, *s: Iterable[T]):
        """Update the set, keeping only elements found in it and all others."""
        in_value = frozenset(s)
        removing = self - in_value
        super().intersection_update(*s)
        self._notify_observers(ObservedAction.REMOVE, removing)

    def difference_update(self, *s: Iterable[T]):
        """Update the set, removing elements found in others."""
        not_removing = super() & frozenset(*s)
        removing = super() - not_removing
        super().remove(removing)
        self._notify_observers(ObservedAction.REMOVE, removing)

    def symmetric_difference_update(self, *s: Iterable[T]):
        """Update the set, keeping only elements found in either set, but not in both."""
        others = frozenset(*s)
        keeping = super() ^ others
        remove_from_self = self - keeping
        self.remove(remove_from_self)  # this will send a remove notification for items that are not in others
        add_from_others = others & keeping
        self.update(add_from_others)  # This will send an add notification for new items from others

    def __ior__(self, other: AbstractSet[T]):
        self.update(other)
        return self

    def __isub__(self, other: AbstractSet[T]):
        self.difference_update(other)
        return self

    def __ixor__(self, other: AbstractSet[T]):
        self.symmetric_difference_update(other)
        return self

    def __iand__(self, other: AbstractSet[T]):
        self.intersection_update(other)
        return self
