class RequiresSelectionError(Exception):
    """Thrown by a command when it is created without any control points selected and
    the command requires control points"""

    def __init__(self, message="No control points selected"):
        self.message = message
        super().__init__(self.message)
