"""Undo and redo for the HUD Preferences editor, without Qt.

The editor's profiles are plain dicts. :class:`History` keeps copies of one
profile: the editor records the profile after each edit, and a recorded state
that differs from the last one is a step to undo. Recording after the fact means
no edit has to announce itself; every action that redraws the profile is
covered.
"""

from __future__ import annotations

import copy
from typing import Any

#: Steps kept per profile; the oldest go first.
LIMIT = 100


class History:
    """The undo and redo steps of one profile."""

    def __init__(self, state: Any, limit: int = LIMIT) -> None:
        self.limit = max(1, int(limit))
        self._baseline = copy.deepcopy(state)
        self._undo: list[Any] = []
        self._redo: list[Any] = []

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def record(self, state: Any) -> bool:
        """Note the profile after an edit; True when it changed since the last note.

        A new edit drops the steps that were undone: they no longer follow.
        """
        if state == self._baseline:
            return False
        self._undo.append(self._baseline)
        del self._undo[: -self.limit]
        self._baseline = copy.deepcopy(state)
        self._redo.clear()
        return True

    def undo(self, current: Any) -> Any | None:
        """The state before the last edit, or None when there is none.

        ``current`` is the profile as it is now: an edit not recorded yet is
        recorded first, so undoing never skips it.
        """
        self.record(current)
        if not self._undo:
            return None
        self._redo.append(self._baseline)
        self._baseline = self._undo.pop()
        return copy.deepcopy(self._baseline)

    def redo(self, current: Any) -> Any | None:
        """The state an undo left, or None when there is none or the profile changed since."""
        if current != self._baseline or not self._redo:
            return None
        self._undo.append(self._baseline)
        self._baseline = self._redo.pop()
        return copy.deepcopy(self._baseline)
