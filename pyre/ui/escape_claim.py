"""Let an active STOS command keep Escape away from the window-level cancel shortcut.

"Cancel registration" is a window-scope Escape ``QAction``. Qt offers the key
to the focus widget first as a ``ShortcutOverride`` event; accepting that event
stops the shortcut and delivers Escape as a normal key press instead. Commands
that already use Escape for themselves (abandon a point create, a box or lasso
select) set ``claims_escape = True``; while one of them is active on a panel,
this filter accepts the override so the command, not the cancel action, gets
the key.
"""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import QEvent, QObject, Qt
from PyQt6.QtGui import QKeyEvent


def command_claims_escape(command: object | None) -> bool:
    """True when *command* handles Escape itself (``claims_escape`` class attribute)."""
    return command is not None and bool(getattr(command, "claims_escape", False))


class EscapeClaimFilter(QObject):
    """Event filter that claims Escape for the active command on the filtered widget."""

    _active_command: Callable[[], object | None]

    def __init__(self, active_command: Callable[[], object | None], parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._active_command = active_command

    def eventFilter(self, watched: QObject | None, event: QEvent | None) -> bool:
        """Accept Escape's ShortcutOverride while the active command claims it."""
        if (event is not None
                and event.type() == QEvent.Type.ShortcutOverride
                and isinstance(event, QKeyEvent)
                and event.key() == Qt.Key.Key_Escape
                and command_claims_escape(self._active_command())):
            event.accept()
            return True
        return False
