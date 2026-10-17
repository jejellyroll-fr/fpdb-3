"""SQLite ``Database.commit`` waits out a lock, and only a lock (#428).

The retry pauses a second between attempts. It used to retry on any exception,
so committing on a disconnected database -- no connection at all -- slept five
seconds before giving up. The Session Guard commits from a Qt timer, so that was
five seconds of frozen window every time it polled a closed database.
"""

import sqlite3

import pytest

from fpdb_3_legacy import Database as database_module
from fpdb_3_legacy.Exceptions import FpdbError


@pytest.fixture
def pauses(monkeypatch) -> list[float]:
    """The pauses commit takes between attempts, recorded instead of slept."""
    taken: list[float] = []
    monkeypatch.setattr(database_module, "sleep", taken.append)
    return taken


class LockedOnce:
    """A connection whose first commit finds the database locked."""

    def __init__(self) -> None:
        self.commits = 0

    def commit(self) -> None:
        self.commits += 1
        if self.commits == 1:
            raise sqlite3.OperationalError("database is locked")


def test_a_disconnected_database_fails_at_once(fresh_db, pauses) -> None:
    fresh_db.disconnect()

    with pytest.raises(FpdbError):
        fresh_db.commit()

    assert pauses == []


def test_a_locked_database_is_still_waited_for(fresh_db, monkeypatch, pauses) -> None:
    connection = LockedOnce()
    monkeypatch.setattr(fresh_db, "connection", connection)

    fresh_db.commit()

    assert connection.commits == 2
    assert pauses == [1]
