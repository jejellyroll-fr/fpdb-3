"""SQLite ``Database.commit`` waits out a lock, and only a lock (#428).

The retry pauses a second between attempts. It used to retry on any exception,
so committing on a disconnected database -- no connection at all -- slept five
seconds before giving up. The Session Guard commits from a Qt timer, so that was
five seconds of frozen window every time it polled a closed database. A full
disk or an I/O error is no more transient than a missing connection.
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


def operational_error(code: int) -> sqlite3.OperationalError:
    """An OperationalError carrying *code*, as sqlite3 raises it."""
    error = sqlite3.OperationalError(f"sqlite error {code}")
    error.sqlite_errorcode = code
    return error


class FailsOnce:
    """A connection whose first commit raises *error*."""

    def __init__(self, error: Exception) -> None:
        self.error = error
        self.commits = 0

    def commit(self) -> None:
        self.commits += 1
        if self.commits == 1:
            raise self.error


def test_a_disconnected_database_fails_at_once(fresh_db, pauses) -> None:
    fresh_db.disconnect()

    with pytest.raises(FpdbError):
        fresh_db.commit()

    assert pauses == []


@pytest.mark.parametrize(
    "code",
    [sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED, sqlite3.SQLITE_BUSY_SNAPSHOT],
    ids=["busy", "locked", "busy-snapshot"],
)
def test_a_locked_database_is_still_waited_for(fresh_db, monkeypatch, pauses, code) -> None:
    connection = FailsOnce(operational_error(code))
    monkeypatch.setattr(fresh_db, "connection", connection)

    fresh_db.commit()

    assert connection.commits == 2
    assert pauses == [1]


@pytest.mark.parametrize("code", [sqlite3.SQLITE_FULL, sqlite3.SQLITE_IOERR], ids=["full", "ioerr"])
def test_an_operational_error_that_is_not_a_lock_fails_at_once(fresh_db, monkeypatch, pauses, code) -> None:
    connection = FailsOnce(operational_error(code))
    monkeypatch.setattr(fresh_db, "connection", connection)

    with pytest.raises(FpdbError):
        fresh_db.commit()

    assert connection.commits == 1
    assert pauses == []
