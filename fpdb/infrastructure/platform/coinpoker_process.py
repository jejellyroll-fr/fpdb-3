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

# ``-logFile .../table_<id>.log`` is the least ambiguous anchor; the trailing
# number of ``roomName=`` / ``pipeName=`` is the fallback. ``\d{4,}`` keeps the
# 2-digit stake components (e.g. "0.01-0.02") from being mistaken for the id.
_LOGFILE_RE = re.compile(r"table_(\d+)\.log")
_ROOMNAME_RE = re.compile(r"(?:room|pipe)Name=.*?(\d{4,})(?:\s|$)")


def extract_table_id(argv: str) -> str | None:
    """Extract a CoinPoker table id from a command line (pure, for testing)."""
    match = _LOGFILE_RE.search(argv) or _ROOMNAME_RE.search(argv)
    return match.group(1) if match else None
