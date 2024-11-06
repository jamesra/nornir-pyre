from typing import Iterable, TypeVar, Generic, Callable, AbstractSet
import enum
from dependency_injector.providers import AbstractSingleton

from . import ObservedAction

T = TypeVar('T')

# The set observer function signature.  It reports which objects were added or removed.  No other actions are possible in sets
SetObserverCallable = Callable[['ObservableSet[T]', ObservedAction, AbstractSet[T] | None], None]


class SetOperation(enum.IntEnum):
    """Helper enum to indicate to a function the type of set operation to be performed"""
    Replace = 0,  # Replace the current set with the new set
    Union = 1,  # Return a new set with elements from the set and all others.
    Intersection = 2,  # Return a new set with elements common to the set and all others.
    Difference = 3,  # Return a new set with elements in the set that are not in the others.
    SymmetricDifference = 4  # Return a new set with elements in either the set or other but not both.


class ObservableSet(set, Generic[T]):
    """A python set that notifies observers when it is modified"""

    def __init__(self, initial_set: Iterable[T] | None = None):
        super(ObservableSet, self).__init__(initial_set if initial_set is not None else [])
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

    def update(self, *others: Iterable[T] | AbstractSet[T]):
        """Update the set, adding elements from all others."""
        if isinstance(*others, int):
            pass

        if not isinstance(*others, Iterable):
            others = frozenset([*others])
        else:
            others = frozenset(*others)
            # intersection = frozenset([others]) - self

        intersection = others - self
        super().update(others)
        self._notify_observers(ObservedAction.ADD, intersection)

    def intersection_update(self, *s: Iterable[T] | AbstractSet[T]):
        """Update the set, keeping only elements found in it and all others."""
        in_value = frozenset(s)
        not_removing = self.intersection(in_value)  # Figure out which items are not being removed
        removing = self - not_removing
        super().intersection_update(*s)
        self._notify_observers(ObservedAction.REMOVE, removing)

    def difference_update(self, *s: Iterable[T] | AbstractSet[T]):
        """Update the set, removing elements found in others."""
        not_removing = self & frozenset(*s)
        removing = self - not_removing
        self.difference_update(*s)
        if len(removing) > 0:
            self._notify_observers(ObservedAction.REMOVE, removing)

    def symmetric_difference_update(self, *s: Iterable[T] | AbstractSet[T]):
        """Update the set, keeping only elements found in either set, but not in both."""
        # You left off here
        others = frozenset(*s)
        original = frozenset(self)
        super().symmetric_difference_update(*s)
        adding = others - original
        removed = original - self

        if len(removed) > 0:
            self._notify_observers(ObservedAction.REMOVE, removed)

        if len(adding) > 0:
            self._notify_observers(ObservedAction.ADD, adding)

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
