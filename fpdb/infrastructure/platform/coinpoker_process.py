"""Shared CoinPoker table-id extraction from a Unity process command line.

CoinPoker renders each open table in its own Unity process and passes the table
identifier on that process's command line, e.g.::

    ... roomName=NL 0.01-0.02 EV-INRIT-(A) 930357 ...
    ... -logFile /Users/.../Library/Logs/CoinPoker/table_930357.log

The on-screen window is owned by the same PID, so ``window -> PID -> argv ->
table id`` is a deterministic mapping that needs no window title, pixel OCR, or
elevated privilege. Only fetching the argv is platform-specific (``ps`` on
macOS, ``psutil`` on Windows); this parser is shared.
"""

from __future__ import annotations

import re
from pathlib import Path

# ``-logFile .../table_<id>.log`` is the least ambiguous anchor; the trailing
# number of ``roomName=`` / ``pipeName=`` is the fallback. ``\d{4,}`` keeps the
# 2-digit stake components (e.g. "0.01-0.02") from being mistaken for the id.
_LOGFILE_RE = re.compile(r"table_(\d+)\.log")
_ROOMNAME_RE = re.compile(r"(?:room|pipe)Name=.*?(\d{4,})(?:\s|$)")
_LOG_PATH_RE = re.compile(r"-logFile\s+(.+?table_\d+\.log)(?:\s|$)")
_TABLE_INIT_RE = re.compile(r"Initializing table .*?RoomName\s*-\s*.*?(\d{4,})\s*$", re.MULTILINE)


def extract_table_id(argv: str) -> str | None:
    """Extract a CoinPoker table id from a command line (pure, for testing)."""
    match = _LOGFILE_RE.search(argv) or _ROOMNAME_RE.search(argv)
    return match.group(1) if match else None


def extract_log_path(argv: str) -> str | None:
    """Return the Unity table log path embedded in a CoinPoker command line."""
    match = _LOG_PATH_RE.search(argv)
    return match.group(1) if match else None


def extract_latest_table_id(log_text: str) -> str | None:
    """Return the most recently initialized room id from a Unity table log."""
    matches = _TABLE_INIT_RE.findall(log_text)
    return matches[-1] if matches else None


def resolve_current_table_id(argv: str) -> str | None:
    """Resolve the live table id, including MTT table-balancing room changes."""
    fallback = extract_table_id(argv)
    log_path = extract_log_path(argv)
    if not log_path:
        return fallback
    try:
        path = Path(log_path)
        with path.open("rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            handle.seek(max(0, size - 131072))
            tail = handle.read().decode("utf-8", errors="replace")
    except OSError:
        return fallback
    return extract_latest_table_id(tail) or fallback
