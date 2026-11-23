"""Persistent capture and replay of hands that failed during import."""

from __future__ import annotations

import atexit
import hashlib
import json
import logging
import os
import tempfile
import threading
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

MAX_ENTRIES = 200
MAX_ENTRY_BYTES = 8 * 1024 * 1024
MAX_TOTAL_BYTES = 32 * 1024 * 1024
log = logging.getLogger(__name__)


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
    """Bounded, persistent registry shared by importers and the Parser Debugger."""

    def __init__(self, storage_path: Path | None = None) -> None:
        self._lock = threading.RLock()
        self._entries: OrderedDict[str, FailedHand] = OrderedDict()
        self._bytes = 0
        self._storage_path = storage_path or Path.home() / ".fpdb" / "failed_hands.json"
        self._dirty = False
        self._save_timer: threading.Timer | None = None
        self._load()

    def _load(self) -> None:
        """Restore valid entries from the user's local fpdb data directory."""
        try:
            payload = json.loads(self._storage_path.read_text(encoding="utf-8"))
            items = payload.get("entries", []) if isinstance(payload, dict) else []
            if not isinstance(items, list):
                return
            for value in items:
                try:
                    entry = FailedHand(
                        key=str(value["key"]),
                        site=str(value["site"]),
                        converter=str(value["converter"]),
                        source=str(value["source"]),
                        mode=str(value["mode"]),
                        timestamp=datetime.fromisoformat(str(value["timestamp"])),
                        hand_index=int(value["hand_index"]),
                        hand_identifier=(str(value["hand_identifier"]) if value.get("hand_identifier") else None),
                        failure_type=str(value["failure_type"]),
                        message=str(value["message"]),
                        raw_text=str(value["raw_text"]),
                        replay_text=str(value["replay_text"]),
                        attempts=max(1, int(value.get("attempts", 1))),
                    )
                except (KeyError, TypeError, ValueError):
                    continue
                size = len(entry.replay_text.encode("utf-8", errors="replace"))
                if size > MAX_ENTRY_BYTES or self._bytes + size > MAX_TOTAL_BYTES:
                    continue
                self._entries[entry.key] = entry
                self._bytes += size
                while len(self._entries) > MAX_ENTRIES:
                    _, removed = self._entries.popitem(last=False)
                    self._bytes -= len(removed.replay_text.encode("utf-8", errors="replace"))
        except FileNotFoundError:
            return
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            log.warning("Could not restore failed hands from %s: %s", self._storage_path, exc)

    def _persist_locked(self) -> None:
        """Atomically persist the bounded queue; errors must not interrupt imports."""
        temp_path: str | None = None
        try:
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "version": 1,
                "entries": [
                    {
                        "key": entry.key,
                        "site": entry.site,
                        "converter": entry.converter,
                        "source": entry.source,
                        "mode": entry.mode,
                        "timestamp": entry.timestamp.isoformat(),
                        "hand_index": entry.hand_index,
                        "hand_identifier": entry.hand_identifier,
                        "failure_type": entry.failure_type,
                        "message": entry.message,
                        "raw_text": entry.raw_text,
                        "replay_text": entry.replay_text,
                        "attempts": entry.attempts,
                    }
                    for entry in self._entries.values()
                ],
            }
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self._storage_path.parent, delete=False
            ) as handle:
                temp_path = handle.name
                json.dump(payload, handle, ensure_ascii=False)
            os.replace(temp_path, self._storage_path)
            self._dirty = False
        except OSError:
            log.exception("Could not persist failed hands to %s", self._storage_path)
            if temp_path is not None:
                try:
                    os.unlink(temp_path)
                except OSError:
                    log.debug("Could not remove temporary failed-hand queue %s", temp_path)

    def _schedule_persist_locked(self) -> None:
        """Coalesce bursts of parser failures into one small periodic disk write."""
        self._dirty = True
        if self._save_timer is not None:
            return
        self._save_timer = threading.Timer(1.0, self.flush)
        self._save_timer.daemon = True
        self._save_timer.start()

    def flush(self) -> None:
        """Write pending changes, including when the application exits."""
        with self._lock:
            if self._save_timer is not None:
                self._save_timer.cancel()
                self._save_timer = None
            if self._dirty:
                self._persist_locked()

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
        if len(replay_text.encode("utf-8", errors="replace")) > MAX_ENTRY_BYTES:
            return None
        now = datetime.now().astimezone()
        with self._lock:
            existing = self._entries.get(key)
            if existing is not None:
                existing.attempts += 1
                self._entries.move_to_end(key)
                self._schedule_persist_locked()
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
            self._schedule_persist_locked()
            return entry

    def entries(self) -> list[FailedHand]:
        with self._lock:
            return list(reversed(self._entries.values()))

    def remove(self, key: str) -> None:
        with self._lock:
            entry = self._entries.pop(key, None)
            if entry is not None:
                self._bytes -= len(entry.replay_text.encode("utf-8", errors="replace"))
                self._schedule_persist_locked()

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._bytes = 0
            self._schedule_persist_locked()


failed_hands = FailedHandRegistry()
atexit.register(failed_hands.flush)
