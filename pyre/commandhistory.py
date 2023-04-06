'''
Created on Apr 10, 2013

@author: u0388504
'''


class CommandHistory(object):
    """Saves and returns objects along with indicies"""

    @property
    def HistoryDepth(self):
        return len(self.History)

    def __init__(self):
        self.History = []
        self.HistoryIndex = 0

    def SaveState(self, recoveryfunc, *args, **kwargs):
        '''Copy the transform points into the undo history.
           Data is the data to pass to the recovery function'''

        if args is None:
            args = []
        if kwargs is None:
            kwargs = {}

        assert (isinstance(kwargs, dict))

        if self.HistoryIndex > 0:
            del self.History[0:self.HistoryIndex]
            self.HistoryIndex = 0

        self.History.insert(0, (recoveryfunc, args, kwargs))

        if len(self.History) > 15:
            del self.History[-1]

    def Undo(self):
        self.HistoryIndex -= 1
        self.RestoreState(self.HistoryIndex)

    def Redo(self):
        self.HistoryIndex += 1
        self.RestoreState(self.HistoryIndex)

    def RestoreState(self, index=None):
        '''Replace current points with points from undo history'''

        if len(self.History) <= 0:
            return

        if index is None:
            index = 0

        if index < 0:
            index = 0
        if index >= len(self.History):
            index = len(self.History) - 1

        print("Restore State #" + str(index))

        (recoveryfunction, args, kwargs) = self.History[index]

        recoveryfunction(*args, **kwargs)


history = CommandHistory()
