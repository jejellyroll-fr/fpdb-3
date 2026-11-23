"""Session-local capture and replay of hands that failed during import."""

from __future__ import annotations

import hashlib
import threading
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from fpdb_3_legacy.i18n import gettext as _

MAX_ENTRIES = 200
MAX_ENTRY_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 32 * 1024 * 1024


@dataclass
class FailedHand:  # pylint: disable=too-many-instance-attributes  # captures all import context for replay
    """A raw failed hand and the context needed to replay it in this session."""

    key: str
    site: str
    converter: str
    source: str
    mode: str
    timestamp: datetime
    hand_index: int
    hand_identifier: str | None
    failure_type: str
    message: str
    raw_text: str
    replay_text: str
    attempts: int = 1


class FailedHandRegistry:
    """Bounded, thread-safe registry shared by bulk and watched-file imports."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._entries: OrderedDict[str, FailedHand] = OrderedDict()
        self._bytes = 0

    def add(
        self,
        *,
        site: str,
        converter: str,
        source: str,
        mode: str,
        hand_index: int,
        failure_type: str,
        message: str,
        raw_text: str,
        shared_header: str = "",
        hand_identifier: str | None = None,
    ) -> FailedHand | None:
        """Keep one copy of a failed hand; repeated watched-file retries only bump its count."""
        raw_size = len(raw_text.encode("utf-8", errors="replace"))
        if raw_size > MAX_ENTRY_BYTES:
            return None
        key = hashlib.sha256(f"{site}\0{raw_text}".encode("utf-8", errors="replace")).hexdigest()
        replay_text = f"{shared_header.rstrip()}\n\n{raw_text.lstrip()}" if shared_header.strip() else raw_text
        now = datetime.now().astimezone()
        with self._lock:
            existing = self._entries.get(key)
            if existing is not None:
                existing.attempts += 1
                self._entries.move_to_end(key)
                return existing
            entry = FailedHand(
                key=key,
                site=site,
                converter=converter,
                source=source,
                mode=mode,
                timestamp=now,
                hand_index=hand_index,
                hand_identifier=hand_identifier,
                failure_type=failure_type,
                message=message,
                raw_text=raw_text,
                replay_text=replay_text,
            )
            entry_size = len(replay_text.encode("utf-8", errors="replace"))
            while self._entries and (
                len(self._entries) >= MAX_ENTRIES or self._bytes + entry_size > MAX_TOTAL_BYTES
            ):
                _, removed = self._entries.popitem(last=False)
                self._bytes -= len(removed.replay_text.encode("utf-8", errors="replace"))
            if entry_size > MAX_TOTAL_BYTES:
                return None
            self._entries[key] = entry
            self._bytes += entry_size
            return entry

    def entries(self) -> list[FailedHand]:
        with self._lock:
            return list(reversed(self._entries.values()))

    def remove(self, key: str) -> None:
        with self._lock:
            entry = self._entries.pop(key, None)
            if entry is not None:
                self._bytes -= len(entry.replay_text.encode("utf-8", errors="replace"))

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._bytes = 0


failed_hands = FailedHandRegistry()


class FailedHandsDialog(QDialog):  # pylint: disable=too-many-instance-attributes  # one attribute per control
    """Session-local queue with direct Parser Debugger replay."""

    def __init__(self, config: Any, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.config = config
        self.setWindowTitle(_("Hands to debug"))
        self.resize(1000, 420)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.table = QTableWidget(0, 7, self)
        self.table.setHorizontalHeaderLabels(
            [_("Site / converter"), _("Source file"), _("Mode"), _("Hand"), _("Failure"), _("Time"), _("Parser message")]
        )
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setWordWrap(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemDoubleClicked.connect(lambda _item: self.replay_selected())

        buttons = QHBoxLayout()
        self.replay_button = QPushButton(_("Open in Parser Debugger"), self)
        self.remove_button = QPushButton(_("Remove"), self)
        self.clear_button = QPushButton(_("Clear list"), self)
        close_button = QPushButton(_("Close"), self)
        self.replay_button.clicked.connect(self.replay_selected)
        self.remove_button.clicked.connect(self.remove_selected)
        self.clear_button.clicked.connect(self.clear_entries)
        close_button.clicked.connect(self.close)
        for button in (self.replay_button, self.remove_button, self.clear_button):
            buttons.addWidget(button)
        buttons.addStretch(1)
        buttons.addWidget(close_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self.table)
        layout.addLayout(buttons)
        self._keys: list[str] = []
        self._signature: tuple[tuple[str, int], ...] | None = None
        self.refresh()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(1500)

    def refresh(self) -> None:
        entries = failed_hands.entries()
        signature = tuple((entry.key, entry.attempts) for entry in entries)
        if signature == self._signature:
            return
        self._signature = signature
        self._keys = [entry.key for entry in entries]
        self.table.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            hand = entry.hand_identifier or str(entry.hand_index)
            if entry.attempts > 1:
                hand = _("{hand} · {attempts} attempts").format(hand=hand, attempts=entry.attempts)
            values = (
                f"{entry.site} · {entry.converter}",
                entry.source,
                entry.mode,
                hand,
                entry.failure_type,
                entry.timestamp.strftime("%Y-%m-%d %H:%M:%S %Z"),
                entry.message,
            )
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(value))
        self.replay_button.setEnabled(bool(entries))
        self.remove_button.setEnabled(bool(entries))
        self.clear_button.setEnabled(bool(entries))

    def _selected_key(self) -> str | None:
        rows = self.table.selectionModel().selectedRows()
        return self._keys[rows[0].row()] if rows and rows[0].row() < len(self._keys) else None

    def replay_selected(self) -> None:
        key = self._selected_key()
        if key is None:
            return
        entry = next((candidate for candidate in failed_hands.entries() if candidate.key == key), None)
        if entry is None:
            self.refresh()
            return
        from fpdb_3_legacy.parser_debugger_dialog import show_parser_debugger

        dialog = show_parser_debugger(self.config, self.parentWidget())
        dialog.load_import_failure(entry.replay_text, entry.site, entry.source)
        dialog.run()

    def remove_selected(self) -> None:
        key = self._selected_key()
        if key is not None:
            failed_hands.remove(key)
            self.refresh()

    def clear_entries(self) -> None:
        failed_hands.clear()
        self.refresh()


def show_failed_hands(config: Any, parent: QWidget | None = None) -> FailedHandsDialog:
    """Open the shared session queue."""
    dialog = FailedHandsDialog(config, parent)
    dialog.show()
    return dialog
