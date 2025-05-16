import abc


class ICommandHistory(abc.ABC):
    """Interface to a command history"""

    @property
    @abc.abstractmethod
    def HistoryDepth(self) -> int:
        """Return the number of commands in the history"""
        raise NotImplementedError()

    @abc.abstractmethod
    def SaveState(self, recoveryfunc, *args, **kwargs):
        """Copy the transform points into the undo history.
           Data is the data to pass to the recovery function"""
        raise NotImplementedError()

    @abc.abstractmethod
    def Undo(self):
        """Undo the last command"""
        raise NotImplementedError()

    @abc.abstractmethod
    def Redo(self):
        """Redo the last command"""
        raise NotImplementedError()

    @abc.abstractmethod
    def RestoreState(self, index: int = None):
        """Replace current points with points from undo history"""
        raise NotImplementedError()
