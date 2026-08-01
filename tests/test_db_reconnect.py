"""Regression tests for surviving a database connection that drops mid-session.

The failure being guarded against: with the database at the far end of a VPN,
a dropped tunnel left the TCP socket in a black hole. Queries never returned and
never raised, so the HUD's Qt event loop and the auto-import worker both stopped
permanently. Two things had to hold for that to be fixable at all --

* the connection must be opened with TCP keepalives, or the error that recovery
  reacts to is never raised in the first place;
* ``reconnect()`` must actually work; it used to pass its arguments positionally
  into a signature that had gained a ``port`` parameter, so the database name
  went in as the port and the user as the database.

Both are asserted below, along with the retry behaviour built on top of them.
"""

import pytest

from fpdb_3_legacy import db_reconnect
from fpdb_3_legacy.Database import Database

psycopg = pytest.importorskip("psycopg")


def make_db(**attrs):
    """Build a Database with only the attributes the connection code touches.

    ``__new__`` skips ``__init__`` (which would open a real connection); the
    methods under test are deliberately narrow enough not to need the rest.
    """
    db = Database.__new__(Database)
    db.backend = Database.PGSQL
    db.host = "192.168.1.10"
    db.port = 5432
    db.database = "fpdb"
    db.user = "fpdb_user"
    db.password = "secret"
    db.connection = None
    db.cursor = None
    db._reconnect_guard = False
    db._reconnect_blocked_until = 0.0
    db._connection_down_logged = False
    db._Database__connected = True
    for name, value in attrs.items():
        setattr(db, name, value)
    return db


class FakeConnection:
    """A psycopg-shaped connection whose queries fail on demand."""

    def __init__(self, fail_with=None) -> None:
        self.fail_with = fail_with
        self.closed = False

    def cursor(self):
        return FakeCursor(self.fail_with)

    def close(self) -> None:
        self.closed = True


class FakeCursor:
    def __init__(self, fail_with=None) -> None:
        self.fail_with = fail_with

    def execute(self, *args) -> None:
        if self.fail_with is not None:
            raise self.fail_with

    def fetchone(self):
        return (1,)

    def close(self) -> None:
        pass


# --------------------------------------------------------------------------
# A. the connection must be opened so that a dead peer becomes a real error
# --------------------------------------------------------------------------


def test_postgresql_connect_arms_keepalives_and_bounds_the_connect(monkeypatch) -> None:
    captured = {}

    def fake_connect(**kwargs):
        captured.update(kwargs)
        return FakeConnection()

    monkeypatch.setattr(psycopg, "connect", fake_connect)
    db = make_db(host="192.168.1.10", _Database__connected=False)
    db._connect_postgresql("192.168.1.10", 5432, "fpdb_user", "secret", "fpdb")

    assert captured["connect_timeout"] == 10
    assert captured["keepalives"] == 1
    assert captured["keepalives_idle"] == 10
    assert captured["keepalives_interval"] == 5
    assert captured["keepalives_count"] == 3
    # Detection window, which is how long the HUD can stall on a dead link.
    idle = captured["keepalives_idle"]
    probes = captured["keepalives_interval"] * captured["keepalives_count"]
    assert idle + probes <= 30


def test_local_peer_connection_also_bounded(monkeypatch) -> None:
    captured = {}

    def fake_connect(**kwargs):
        captured.update(kwargs)
        return FakeConnection()

    monkeypatch.setattr(psycopg, "connect", fake_connect)
    db = make_db(host="localhost", _Database__connected=False)
    db._connect_postgresql("localhost", 5432, "fpdb_user", "secret", "fpdb")

    assert captured["dbname"] == "fpdb"
    assert captured["connect_timeout"] == 10


# --------------------------------------------------------------------------
# B. reconnect, and the retry built on it
# --------------------------------------------------------------------------


def test_reconnect_passes_each_parameter_to_its_own_slot() -> None:
    """The positional call used to shift database into port and user into database."""
    captured = {}
    db = make_db()
    db.disconnect = lambda due_to_error=False: None
    db.connect = lambda **kwargs: captured.update(kwargs)

    db.reconnect(due_to_error=True)

    assert captured == {
        "backend": Database.PGSQL,
        "host": "192.168.1.10",
        "port": 5432,
        "database": "fpdb",
        "user": "fpdb_user",
        "password": "secret",
    }


def test_dropped_connection_is_reconnected_and_the_query_replayed() -> None:
    attempts = []

    class Db:
        backend = Database.PGSQL

        def __init__(self) -> None:
            self.recoveries = 0

        def recover_connection(self) -> bool:
            self.recoveries += 1
            return True

        @db_reconnect.reconnect_on_connection_loss
        def get_table_info(self, hand_id):
            attempts.append(hand_id)
            if len(attempts) == 1:
                msg = "consuming input failed: server closed the connection unexpectedly"
                raise psycopg.OperationalError(msg)
            return ("Table 1", 6)

    db = Db()
    assert db.get_table_info(42) == ("Table 1", 6)
    assert attempts == [42, 42]
    assert db.recoveries == 1


def test_ordinary_sql_error_is_reported_not_retried() -> None:
    attempts = []

    class Db:
        backend = Database.PGSQL
        recoveries = 0

        def recover_connection(self) -> bool:
            self.recoveries += 1
            return True

        @db_reconnect.reconnect_on_connection_loss
        def get_table_info(self, hand_id):
            attempts.append(hand_id)
            msg = 'column "nope" does not exist'
            raise psycopg.ProgrammingError(msg)

    db = Db()
    with pytest.raises(psycopg.ProgrammingError):
        db.get_table_info(42)
    assert attempts == [42]
    assert db.recoveries == 0


def test_failed_recovery_lets_the_original_error_through() -> None:
    class Db:
        backend = Database.PGSQL

        def recover_connection(self) -> bool:
            return False

        @db_reconnect.reconnect_on_connection_loss
        def get_table_info(self, hand_id):
            msg = "server closed the connection unexpectedly"
            raise psycopg.OperationalError(msg)

    with pytest.raises(psycopg.OperationalError):
        Db().get_table_info(42)


def test_nested_decorated_calls_recover_only_once() -> None:
    """One dropped connection must cost one reconnect, not one per call layer."""
    inner_attempts = []

    class Db:
        backend = Database.PGSQL

        def __init__(self) -> None:
            self.recoveries = 0

        def recover_connection(self) -> bool:
            self.recoveries += 1
            return True

        @db_reconnect.reconnect_on_connection_loss
        def get_gameinfo(self, hand_id):
            inner_attempts.append(hand_id)
            if len(inner_attempts) == 1:
                msg = "server closed the connection unexpectedly"
                raise psycopg.OperationalError(msg)
            return {"gametypeId": 7}

        @db_reconnect.reconnect_on_connection_loss
        def get_stats_from_hand(self, hand_id):
            return self.get_gameinfo(hand_id)

    db = Db()
    assert db.get_stats_from_hand(42) == {"gametypeId": 7}
    assert db.recoveries == 1


def test_sqlite_failures_are_never_treated_as_a_lost_connection() -> None:
    """SQLite has no socket to lose; retrying would just repeat a real error."""
    err = Exception("database is locked")
    assert db_reconnect.is_connection_lost(Database.SQLITE, err) is False


# --------------------------------------------------------------------------
# recover_connection: bounded, and quiet while the database stays away
# --------------------------------------------------------------------------


def test_recover_connection_backs_off_after_a_failure() -> None:
    """A database that stays down must not cost a connect timeout per query."""
    attempts = []

    def failing_reconnect(due_to_error=False):
        attempts.append(due_to_error)
        msg = "connection to server failed: Operation timed out"
        raise psycopg.OperationalError(msg)

    db = make_db()
    db.reconnect = failing_reconnect

    assert db.recover_connection() is False
    assert db.recover_connection() is False
    assert db.recover_connection() is False
    assert len(attempts) == 1, "cooldown should suppress the follow-up attempts"
    assert db._reconnect_blocked_until > 0


def test_recover_connection_clears_the_backoff_once_it_succeeds() -> None:
    db = make_db(_reconnect_blocked_until=0.0, _connection_down_logged=True)

    def stub_reconnect(due_to_error=False):
        db._Database__connected = True

    db.reconnect = stub_reconnect

    assert db.recover_connection() is True
    assert db._reconnect_blocked_until == 0.0
    assert db._connection_down_logged is False


def test_force_disconnect_survives_a_broken_connection() -> None:
    """The normal disconnect commits on the way out, which a dead socket cannot."""

    class BrokenConnection:
        def close(self) -> None:
            msg = "the connection is closed"
            raise psycopg.OperationalError(msg)

        def commit(self) -> None:
            msg = "the connection is closed"
            raise psycopg.OperationalError(msg)

    db = make_db(connection=BrokenConnection())
    db._force_disconnect()

    assert db.connection is None
    assert db.is_connected() is False


# --------------------------------------------------------------------------
# ensure_connection: the seam the auto-import cycle uses
# --------------------------------------------------------------------------


def test_ensure_connection_accepts_a_live_connection() -> None:
    db = make_db(connection=FakeConnection())
    assert db.ensure_connection() is True


def test_ensure_connection_recovers_a_dead_one() -> None:
    dead = FakeConnection(fail_with=psycopg.OperationalError("server closed the connection"))
    db = make_db(connection=dead)

    def stub_reconnect(due_to_error=False):
        # What the real connect() does on success, and what recover_connection
        # reads back before reporting that the caller may query again.
        db.connection = FakeConnection()
        db._Database__connected = True

    db.reconnect = stub_reconnect

    assert db.ensure_connection() is True
    assert db.connection is not dead
    assert dead.closed is True
