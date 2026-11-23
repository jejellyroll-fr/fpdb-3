"""Session-local capture and replay of hands that failed during import."""

from __future__ import annotations

import hashlib
import threading
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime

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
