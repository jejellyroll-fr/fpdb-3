"""The replayer's "Action history" window (#825): click an entry to seek the replay to it.

The entries come from :func:`fpdb_3_legacy.replay_history.replay_history_entries`;
this window only lists them, keeps the current one selected while the hand is
stepped, and asks the replayer to seek when one is clicked or activated.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QKeyEvent
from PySide6.QtWidgets import QDialog, QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from fpdb_3_legacy.i18n import gettext as _
from fpdb_3_legacy.replay_history import ACTION, ReplayHistoryEntry, history_row_for_index

# Keys the replayer handles that keep working while this window has the focus.
_FORWARDED_KEYS = {
    Qt.Key.Key_Left,
    Qt.Key.Key_Right,
    Qt.Key.Key_Space,
    Qt.Key.Key_Home,
    Qt.Key.Key_End,
}

_ENTRY_ROLE = Qt.ItemDataRole.UserRole


class ReplayHistoryDialog(QDialog):
    """A non-modal list of the hand's phases and actions."""

    def __init__(
        self,
        parent: QWidget | None,
        seek: Callable[[int], None],
        forward_key: Callable[[QKeyEvent], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(_("Action history"))
        self.setModal(False)
        self.resize(380, 560)
        self._seek = seek
        self._forward_key = forward_key
        self.entries: list[ReplayHistoryEntry] = []
        self.blind = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)
        self.hint = QLabel(_("Click an action, or select it and press Enter, to jump to it."))
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)

        self.list = QListWidget()
        self.list.setObjectName("replayHistoryList")
        self.list.setUniformItemSizes(True)
        self.list.itemClicked.connect(self._item_chosen)
        self.list.itemActivated.connect(self._item_chosen)
        # The list would take A (type-ahead search) and the arrows for itself.
        self.list.installEventFilter(self)
        layout.addWidget(self.list)

    def set_entries(self, entries: Sequence[ReplayHistoryEntry], current_index: int, blind=None) -> None:
        """Replace the listed entries, then select the one for *current_index*."""
        self.entries = list(entries)
        self.blind = blind
        self.list.blockSignals(True)
        try:
            self.list.clear()
            for entry in self.entries:
                item = QListWidgetItem(entry.text)
                item.setData(_ENTRY_ROLE, entry.index)
                if entry.kind != ACTION:
                    font = QFont(self.list.font())
                    font.setBold(True)
                    item.setFont(font)
                    item.setForeground(QBrush(QColor("#8fa3b3")))
                self.list.addItem(item)
        finally:
            self.list.blockSignals(False)
        self.sync(current_index)

    def sync(self, current_index: int) -> None:
        """Select the entry of the state the replayer shows, without seeking."""
        current = self.list.currentRow()
        if 0 <= current < len(self.entries) and self.entries[current].index == current_index:
            # Several entries can share a state (the winners at the end): keep the one clicked.
            return
        row = history_row_for_index(self.entries, current_index)
        self.list.blockSignals(True)
        try:
            if row is None:
                self.list.clearSelection()
                self.list.setCurrentRow(-1)
            else:
                self.list.setCurrentRow(row)
                self.list.scrollToItem(self.list.item(row))
        finally:
            self.list.blockSignals(False)

    def current_entry(self) -> ReplayHistoryEntry | None:
        """The entry selected in the list, if any."""
        row = self.list.currentRow()
        return self.entries[row] if 0 <= row < len(self.entries) else None

    def _item_chosen(self, item: QListWidgetItem) -> None:
        index = item.data(_ENTRY_ROLE)
        if index is not None:
            self._seek(int(index))

    def _handle_key(self, event: QKeyEvent) -> bool:
        """A closes the window and the replayer's stepping keys step the replay."""
        if event.key() == Qt.Key.Key_A and event.modifiers() == Qt.KeyboardModifier.NoModifier:
            self.close()
            return True
        if event.key() in _FORWARDED_KEYS and self._forward_key is not None:
            self._forward_key(event)
            return True
        return False

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802  # pylint: disable=invalid-name
        """Route the list's key presses through :meth:`_handle_key` (Qt override)."""
        if watched is self.list and event.type() == QEvent.Type.KeyPress and isinstance(event, QKeyEvent):
            if self._handle_key(event):
                return True
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802  # pylint: disable=invalid-name
        """Handle A and the stepping keys, then the dialog's own keys (Qt override)."""
        if not self._handle_key(event):
            super().keyPressEvent(event)
