"""What the Log Messages window shows, without Qt (#456).

``GuiLogView`` used to parse the log files, filter their lines and build the
clipboard text inside its Qt models and slots, where an exception is swallowed
by the event loop and nothing could be tested without a window. Those
decisions live here; the window only wires them to widgets.

fpdb and the HUD write one JSON object per line (``loggingFpdb.JsonFormatter``)
to ``fpdb-log.txt`` and ``HUD-log.txt``, rotated into dated ``-partN`` files
beside them.
"""

from __future__ import annotations

import json
import os
from collections import deque
from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

#: The levels the window can filter on, in the order its boxes appear.
LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")

#: The colour each level is drawn in; another level takes the palette's text colour.
LEVEL_COLOURS = {"DEBUG": "green", "INFO": "white", "WARNING": "orange", "ERROR": "red"}

#: The two logs the window offers, rotated files included: fpdb's and the HUD's.
LOG_PATTERNS = ("fpdb-log*.txt", "HUD-log*.txt")

#: How many of the newest lines a log is read for.
MAX_LOG_ENTRIES = 1000


@dataclass(frozen=True)
class LogEntry:
    """One log record, as the window's five columns show it."""

    level: str
    logged_at: str
    module: str
    function: str
    message: str

    def as_row(self) -> list[str]:
        return [self.level, self.logged_at, self.module, self.function, self.message]


@dataclass(frozen=True)
class LogFile:
    """A log the window can open, and when it was last written."""

    path: str
    modified: datetime

    @property
    def name(self) -> str:
        return os.path.basename(self.path)


def parse_line(line: str) -> LogEntry | None:
    """The record a log line holds, or None for a blank line or one that is not a record."""
    text = line.strip()
    if not text:
        return None
    try:
        record = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(record, dict):
        return None

    def field(name: str) -> str:
        return str(record.get(name) or "").strip()

    return LogEntry(
        level=field("levelname").upper(),
        logged_at=field("asctime"),
        module=field("module"),
        function=field("funcName"),
        message=field("message"),
    )


def read_tail(path: str | os.PathLike[str], max_entries: int = MAX_LOG_ENTRIES) -> list[LogEntry]:
    """The records among the last ``max_entries`` lines of a log, oldest first; none when it is missing."""
    try:
        with open(path, encoding="utf-8", errors="replace") as stream:
            lines = deque(stream, maxlen=max_entries)
    except FileNotFoundError:
        return []
    return [entry for entry in map(parse_line, lines) if entry is not None]


def matches(level: str | None, module: str | None, levels: Collection[str], module_text: str) -> bool:
    """Whether a row with this level and module passes the window's filters.

    A row with no level is a row the model cannot describe, so it is hidden.
    The module filter is a case-insensitive substring; an empty one matches all.
    """
    if level is None or level.strip().upper() not in {wanted.upper() for wanted in levels}:
        return False
    wanted = module_text.strip().lower()
    return not wanted or wanted in (module or "").lower()


def log_files(log_dir: str | os.PathLike[str]) -> list[LogFile]:
    """The fpdb and HUD logs in ``log_dir``, rotated ones included, newest first."""
    found: dict[str, LogFile] = {}
    for pattern in LOG_PATTERNS:
        for path in Path(log_dir).glob(pattern):
            try:
                modified = datetime.fromtimestamp(path.stat().st_mtime)
            except OSError:
                continue
            found[str(path)] = LogFile(str(path), modified)
    return sorted(found.values(), key=lambda log: log.modified, reverse=True)


def rows_as_text(rows: Iterable[Sequence[object]]) -> str:
    """Rows as the clipboard gets them: tab between columns, one line per row."""
    return "".join("\t".join(str(value) for value in row) + "\n" for row in rows)
