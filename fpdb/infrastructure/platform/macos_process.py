"""Resolve a macOS poker-table window to its in-app table id via process argv.

CoinPoker renders each open table in its own Unity process
(``CoinPoker Game.app``) and passes the table identifier directly on that
process's command line, e.g.::

    ... roomName=PLO 0.01-0.02 EV-INRIT-ANTE (A) 922564 ...
    ... -logFile /Users/.../Library/Logs/CoinPoker/table_922564.log

The on-screen window created by that process is owned by the same PID, which
Quartz exposes as ``kCGWindowOwnerPID`` regardless of Screen Recording
permission. So ``window -> PID -> argv -> table id`` is a fully deterministic
mapping that needs no pixel OCR, no window title, no DevTools port, and no
elevated privilege — it only reads process arguments already visible to ``ps``.

Returns ``None`` (never raises) when the table id cannot be resolved, so callers
can fall back to OCR or the existing heuristics.
"""

from __future__ import annotations

import logging
import subprocess
import time

# extract_table_id is re-exported for callers and tests that import it here.
from .coinpoker_process import extract_table_id as extract_table_id
from .coinpoker_process import resolve_current_table_id

logger = logging.getLogger(__name__)

# argv is stable for a table's lifetime; cache per PID to avoid re-spawning ps on
# every HUD poll.
_TTL = 5.0
_cache: dict[int, tuple[float, str | None]] = {}


def _argv_for_pid(pid: int) -> str:
    proc = subprocess.run(
        ["ps", "-ww", "-p", str(pid), "-o", "args="],
        capture_output=True,
        text=True,
        timeout=2,
    )
    return proc.stdout.strip()


def table_id_for_pid(pid: int, *, force: bool = False) -> str | None:
    """Return the CoinPoker table id owned by ``pid``, or ``None``.

    Cached per PID for a few seconds.
    """
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return None
    if pid <= 0:
        return None

    now = time.monotonic()
    hit = _cache.get(pid)
    if hit and not force and now - hit[0] < _TTL:
        return hit[1]

    table_id: str | None = None
    try:
        table_id = resolve_current_table_id(_argv_for_pid(pid))
    except Exception as exc:  # pragma: no cover - platform dependent
        logger.debug("Could not read argv for pid %s: %s", pid, exc)

    _cache[pid] = (now, table_id)
    return table_id
