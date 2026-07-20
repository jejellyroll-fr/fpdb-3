"""Resolve a Windows CoinPoker table window to its table id via process argv.

Windows counterpart of ``macos_process``: CoinPoker renders each open table in
its own Unity process (``...\\CoinPoker Game\\CoinPoker.exe``) whose command line
carries the table id (``roomName=... <id>`` / ``-logFile ...\\table_<id>.log``).
A window resolves to that process via ``GetWindowThreadProcessId``, so
``window -> PID -> argv -> table id`` tells multiple open tables apart with no
window title, pixel OCR, or elevated privilege. The argv is read with ``psutil``
(already a dependency) rather than shelling out.

Returns ``None`` (never raises) when the table id cannot be resolved, so callers
can fall back to the window-class heuristic.
"""

from __future__ import annotations

import logging
import time

from .coinpoker_process import extract_table_id

logger = logging.getLogger(__name__)

# argv is stable for a table's lifetime; cache per PID to avoid re-reading it on
# every HUD poll.
_TTL = 5.0
_cache: dict[int, tuple[float, str | None]] = {}


def _argv_for_pid(pid: int) -> str:
    import psutil

    return " ".join(psutil.Process(pid).cmdline())


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
        table_id = extract_table_id(_argv_for_pid(pid))
    except Exception as exc:  # pragma: no cover - platform/psutil dependent
        logger.debug("Could not read argv for pid %s: %s", pid, exc)

    _cache[pid] = (now, table_id)
    return table_id
