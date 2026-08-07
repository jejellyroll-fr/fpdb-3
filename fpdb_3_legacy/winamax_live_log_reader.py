"""Real-time log reader for Winamax application log files.

Monitors Winamax log files (~/Library/Application Support/winamax/logs/*.log)
in real time to extract table hand starts, seated player logins, and actions
for instant Fast-Fold / Escape HUD updates.
"""

from __future__ import annotations

import logging
import os
import platform
import re
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


def get_winamax_log_dir() -> Path | None:
    """Return Path to Winamax application logs directory if present."""
    sys_name = platform.system()
    candidates: list[Path] = []

    if sys_name == "Darwin":
        candidates.append(Path.home() / "Library" / "Application Support" / "winamax" / "logs")
    elif sys_name == "Linux":
        candidates.append(Path.home() / ".config" / "winamax" / "logs")
        candidates.append(Path.home() / ".winamax" / "logs")
    elif sys_name == "Windows":
        appdata = os.environ.get("APPDATA")
        localdata = os.environ.get("LOCALAPPDATA")
        if appdata:
            candidates.append(Path(appdata) / "Winamax" / "logs")
        if localdata:
            candidates.append(Path(localdata) / "Winamax" / "logs")

    for path in candidates:
        if path.is_dir():
            return path

    return None


def get_latest_winamax_log_file(log_dir: Path | None = None) -> Path | None:
    """Return path to the latest Winamax .log file by modification time."""
    target_dir = log_dir or get_winamax_log_dir()
    if not target_dir or not target_dir.is_dir():
        return None

    log_files = list(target_dir.glob("*.log"))
    if not log_files:
        return None

    return max(log_files, key=lambda f: f.stat().st_mtime)


class WinamaxLiveLogReader:
    """Tails active Winamax application log file to detect real-time seat and hand changes."""

    # 1786129601014 inf [table] 1 gf.cgmatchmaker.gf_1.t22754010.0 hand 22754010-6399-1786129600
    RE_HAND_START = re.compile(
        r"\[table\]\s+(?P<tbl_no>\d+)\s+(?P<pool>[^\s]+)\s+hand\s+(?P<hand_id>[^\s]+)",
        re.IGNORECASE,
    )
    # 1786129601015 inf [table] 1 gf.cgmatchmaker.gf_1.t22754010.0 action SB login="Player01" amount="0.01"
    RE_ACTION = re.compile(
        r"\[table\]\s+(?P<tbl_no>\d+)\s+(?P<pool>[^\s]+)\s+action\s+(?P<action_type>[^\s]+)\s+login=\"(?P<login>[^\"]+)\"",
        re.IGNORECASE,
    )

    def __init__(
        self,
        on_seat_update: Callable[[str, dict[int, str]], None] | None = None,
        poll_interval: float = 0.2,
    ) -> None:
        self.on_seat_update = on_seat_update
        self.poll_interval = poll_interval
        self._running = False
        self._thread: threading.Thread | None = None
        self._table_players: dict[str, dict[int, str]] = {}
        self._current_hand_players: dict[str, list[str]] = {}

    def parse_log_line(self, line: str) -> dict[str, Any] | None:
        """Parse a single line from Winamax application log file."""
        if "hand" in line and (m := self.RE_HAND_START.search(line)):
            tbl_no = m.group("tbl_no")
            pool = m.group("pool")
            hand_id = m.group("hand_id")
            return {
                "event": "hand_start",
                "table_no": tbl_no,
                "pool": pool,
                "hand_id": hand_id,
            }

        if "login=" in line and (m := self.RE_ACTION.search(line)):
            tbl_no = m.group("tbl_no")
            pool = m.group("pool")
            action_type = m.group("action_type")
            login = m.group("login")
            return {
                "event": "action",
                "table_no": tbl_no,
                "pool": pool,
                "action_type": action_type,
                "login": login,
            }

        return None

    def process_line(self, line: str) -> None:
        """Process log line and update table player mappings."""
        parsed = self.parse_log_line(line)
        if not parsed:
            return

        pool = parsed.get("pool", "default")
        event = parsed.get("event")

        if event == "hand_start":
            self._current_hand_players[pool] = []

        elif event == "action":
            login = parsed.get("login")
            if login and login not in self._current_hand_players.get(pool, []):
                self._current_hand_players.setdefault(pool, []).append(login)

                # Rebuild seat map
                seat_map = {idx + 1: player for idx, player in enumerate(self._current_hand_players[pool])}
                self._table_players[pool] = seat_map

                if self.on_seat_update:
                    try:
                        self.on_seat_update(pool, seat_map)
                    except Exception:
                        log.exception("Error in on_seat_update callback:")

    def start(self) -> None:
        """Start background log watcher thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop background log watcher thread."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def _watch_loop(self) -> None:
        """Background loop tailing active Winamax log file."""
        log_file = get_latest_winamax_log_file()
        if not log_file:
            log.warning("No Winamax log file found in %s", get_winamax_log_dir())

        file_obj = None
        current_path = None

        while self._running:
            try:
                latest = get_latest_winamax_log_file()
                if latest != current_path:
                    if file_obj:
                        file_obj.close()
                    current_path = latest
                    if latest:
                        file_obj = open(latest, encoding="utf-8", errors="ignore")
                        file_obj.seek(0, os.SEEK_END)
                        log.info("Started tailing Winamax log file: %s", latest)

                if file_obj:
                    while line := file_obj.readline():
                        self.process_line(line)

            except Exception:
                log.exception("Error reading Winamax live log:")

            time.sleep(self.poll_interval)

        if file_obj:
            file_obj.close()
