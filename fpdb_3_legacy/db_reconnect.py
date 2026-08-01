"""Recovery from a lost database connection.

Why this exists
---------------
fpdb keeps one long-lived connection per process (HUD, importer, GUI). When the
database lives at the other end of a VPN or a flaky Wi-Fi link, that connection
does not fail cleanly: the tunnel drops, the TCP socket is left in a black hole,
and the next ``execute()`` blocks inside the kernel's retransmit loop. No
exception is ever raised, so no ``try/except`` can react -- the HUD's Qt event
loop and the auto-import worker simply stop, for good.

Two pieces are needed to fix that, and both live here:

1. ``PG_NETWORK_KWARGS`` / ``MYSQL_NETWORK_KWARGS`` (applied by ``Database``)
   arm TCP keepalives so a dead peer surfaces as a real error within about a
   minute instead of never.
2. ``is_connection_lost`` plus the ``reconnect_on_connection_loss`` decorator
   turn that error into a transparent reconnect-and-retry.

Ordering matters: without (1) the errors in (2) never happen.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any

from fpdb_3_legacy.loggingFpdb import get_logger

log = get_logger("database")


# libpq connection parameters. ``keepalives_idle``/``interval``/``count`` mean a
# silently dead peer is detected after roughly 30 + 3*10 = 60 seconds, even in
# the middle of a query that is waiting for a result. ``connect_timeout`` bounds
# the reconnect attempts themselves, which is what keeps the recovery path from
# becoming the new place where everything hangs.
PG_NETWORK_KWARGS: dict[str, Any] = {
    "connect_timeout": 10,
    "keepalives": 1,
    "keepalives_idle": 30,
    "keepalives_interval": 10,
    "keepalives_count": 3,
}

# MySQL over the same VPN has the same failure mode; MySQLdb/pymysql expose the
# connect timeout but leave keepalives to the OS defaults.
MYSQL_NETWORK_KWARGS: dict[str, Any] = {
    "connect_timeout": 10,
}

# Seconds to wait before attempting another reconnect after one has failed.
# Without this, every hand the HUD receives while the VPN is down would pay a
# full ``connect_timeout``, which is precisely the stall we are removing.
RECONNECT_COOLDOWN = 10.0

# MySQL server error codes that mean the connection itself is gone.
_MYSQL_LOST_CONNECTION_CODES = frozenset({2006, 2013, 2055, 4031})

# Fallback for drivers/wrappers that report a dead socket through a plain
# exception type. Matched case-insensitively against ``str(exc)``.
_LOST_CONNECTION_MARKERS = (
    "server closed the connection",
    "connection already closed",
    "the connection is closed",
    "connection not open",
    "consuming input failed",
    "ssl connection has been closed",
    "terminating connection",
    "no connection to the server",
    "broken pipe",
    "connection reset by peer",
    "connection timed out",
    "server has gone away",
    "lost connection to",
    "eof detected",
)


def _psycopg_lost(exc: BaseException) -> bool:
    """Report whether a psycopg exception means the connection died."""
    try:
        import psycopg
    except ImportError:  # backend not installed in this process
        return False
    # psycopg3 raises OperationalError for anything the network did to us and
    # InterfaceError for using a connection that is already gone.
    return isinstance(exc, (psycopg.OperationalError, psycopg.InterfaceError))


def _mysql_lost(exc: BaseException) -> bool:
    """Report whether a MySQLdb/pymysql exception means the connection died."""
    try:
        import MySQLdb
    except ImportError:
        return False
    if isinstance(exc, MySQLdb.InterfaceError):
        return True
    if isinstance(exc, MySQLdb.OperationalError):
        code = exc.args[0] if exc.args else None
        return code in _MYSQL_LOST_CONNECTION_CODES
    return False


def is_connection_lost(backend: int, exc: BaseException) -> bool:
    """Tell a dead connection apart from an ordinary SQL error.

    Only the networked backends can lose a connection, so SQLite always answers
    False: retrying a SQLite failure would just repeat a genuine error (a locked
    file, a constraint violation) at twice the cost.

    Args:
        backend: The ``Database.PGSQL`` / ``MYSQL_INNODB`` / ``SQLITE`` constant.
        exc: The exception raised while running a query.

    Returns:
        True when reconnecting is a sensible response to ``exc``.
    """
    from fpdb_3_legacy.Database import Database

    if backend == Database.SQLITE:
        return False
    if backend == Database.PGSQL and _psycopg_lost(exc):
        return True
    if backend == Database.MYSQL_INNODB and _mysql_lost(exc):
        return True
    text = str(exc).lower()
    return any(marker in text for marker in _LOST_CONNECTION_MARKERS)


def reconnect_on_connection_loss(func: Callable) -> Callable:
    """Reconnect once and replay ``func`` when the connection drops mid-query.

    Meant for read-only ``Database`` methods that a long-running process calls
    repeatedly -- the HUD's per-hand lookups above all. Writes are deliberately
    left out: replaying half of a transaction is not something a decorator can
    reason about, so the importer instead checks the connection between files
    (see ``Importer.runUpdated``).

    Nested decorated calls are collapsed: only the outermost one owns the retry,
    so a single dropped connection costs one reconnect rather than one per layer.
    """

    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        if getattr(self, "_reconnect_guard", False):
            # An enclosing decorated call already owns the retry for this query.
            return func(self, *args, **kwargs)
        self._reconnect_guard = True
        try:
            try:
                return func(self, *args, **kwargs)
            except Exception as exc:
                if not is_connection_lost(self.backend, exc):
                    raise
                log.warning(
                    "Database connection lost during %s (%s); attempting to reconnect.",
                    func.__name__,
                    exc,
                )
                if not self.recover_connection():
                    raise
                return func(self, *args, **kwargs)
        finally:
            self._reconnect_guard = False

    return wrapper
