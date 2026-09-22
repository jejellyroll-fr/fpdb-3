"""A borrowed database connection for research workers, Qt free (#366).

The research panes all run their queries off the Qt event loop, and a thread
must not share the widget's cursor. This is the one place that says how a
worker gets its own connection, so a second pane needing one does not have to
copy a context manager out of a GUI module.
"""

from __future__ import annotations

import contextlib
from typing import Any


class WorkerDatabase:
    """Small read-only Database facade around a borrowed DB-API connection."""

    def __init__(self, owner: Any, connection: Any) -> None:
        self.backend = owner.backend
        self.sql = owner.sql
        self._connection = connection

    def get_cursor(self):
        return self._connection.cursor()


@contextlib.contextmanager
def worker_database(db: Any):
    """Give research workers a dedicated connection when the DB supports it."""
    acquire = getattr(db, "worker_connection", None)
    if callable(acquire):
        with acquire() as connection:
            yield WorkerDatabase(db, connection)
    else:
        # Lightweight test doubles and legacy adapters may not expose the pool.
        yield db


__all__ = ["WorkerDatabase", "worker_database"]
