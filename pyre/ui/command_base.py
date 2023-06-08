'''
Created on Feb 10, 2015

@author: u0490822
'''


class CommandBase(object):
    '''
    interface for commands
    '''

    @property
    def parent(self):
        '''Parent window the command is bound to and subscribes to events from'''
        return self._parent

    def end_command(self):
        '''function called when the command is finished'''
        if not self._command_completed is None:
            self._command_completed(self)

        self.unsubscribe_to_parent()

    def unsubscribe_to_parent(self):
        raise NotImplemented(
            "All commands should implement unsubscribe_to_parent which executes when the command is completed")

    def __init__(self, parent, completed_func):
        '''
        :param window parent: Window to subscribe to for events
        :param func completed_func: Function to call when command has completed
        '''

        self._parent = parent
        self._command_completed = completed_func
        pass


class VolumeCommandBase(CommandBase):
    '''
    A command that needs to handle the mouse position in terms 
    '''

    @property
    def camera(self):
        '''The camera used by the command.'''
        return self._camera

    def GetCorrectedMousePosition(self, e):
        '''wxPython inverts the mouse position, flip it back'''
        (x, y) = e.GetPositionTuple()
        return self.camera.WindowHeight - y, x

    def _mouse_position_in_volume(self, e):
        (x, y) = e.GetPositionTuple()
        (self.camera.WindowHeight - y, x)
        (y, x) = self._get_corrected_mouse_position_func(e)

    def __init__(self, parent, completed_func, camera):
        '''
        :param window parent: Window to subscribe to for events
        :param func completed_func: Function to call when command has completed
        :param Camera camera: Camera to use for mapping screen to volume coordinates
        '''

        super(VolumeCommandBase, self).__init__(parent, completed_func)

        self._camera = camera
