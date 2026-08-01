"""Tests for the database round-trip counter.

The number that decides how the HUD feels over a VPN is how many statements it
issues per hand and per table: each one costs a network latency whatever the
server does with it. These cover the counting itself, the attribution to the
work that asked for the statements, and the fact that the whole thing stays out
of the way when it is switched off.
"""

from __future__ import annotations

import sqlite3

import pytest

from fpdb_3_legacy import db_profile


@pytest.fixture
def on(monkeypatch):
    """Switch profiling on and hand back a clean process-wide profile."""
    monkeypatch.setenv(db_profile.ENV_FLAG, "1")
    profile = db_profile.get_profile()
    profile.reset()
    yield profile
    profile.reset()


@pytest.fixture
def connection():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO t (name) VALUES ('a'), ('b')")
    conn.commit()
    yield conn
    conn.close()


# -- counting -------------------------------------------------------------


def test_every_statement_is_counted(on, connection) -> None:
    counted = db_profile.wrap_connection(connection)

    c = counted.cursor()
    c.execute("SELECT * FROM t")
    c.fetchall()
    c.execute("SELECT COUNT(*) FROM t")
    c.fetchone()

    assert on.total.calls == 2
    assert on.total.seconds > 0


def test_a_failing_statement_still_cost_a_round_trip(on, connection) -> None:
    """Hiding failures would flatter the report; the packets still went out."""
    counted = db_profile.wrap_connection(connection)

    with pytest.raises(sqlite3.OperationalError):
        counted.cursor().execute("SELECT * FROM nope")

    assert on.total.calls == 1


def test_results_still_come_back_through_the_wrapper(on, connection) -> None:
    counted = db_profile.wrap_connection(connection)

    c = counted.cursor()
    c.execute("SELECT name FROM t ORDER BY name")

    assert [row[0] for row in c.fetchall()] == ["a", "b"]


def test_the_connection_is_otherwise_transparent(on, connection) -> None:
    """The dialects set autocommit on the connection; that must reach the real one."""
    counted = db_profile.wrap_connection(connection)

    assert hasattr(counted, "commit")
    counted.isolation_level = None
    assert connection.isolation_level is None
    counted.commit()


def test_nothing_is_wrapped_when_profiling_is_off(monkeypatch, connection) -> None:
    monkeypatch.delenv(db_profile.ENV_FLAG, raising=False)

    assert db_profile.wrap_connection(connection) is connection


def test_wrapping_twice_does_not_double_count(on, connection) -> None:
    counted = db_profile.wrap_connection(db_profile.wrap_connection(connection))

    counted.cursor().execute("SELECT 1")

    assert on.total.calls == 1


# -- attribution ----------------------------------------------------------


def test_a_statement_counts_for_every_scope_it_ran_inside(on, connection) -> None:
    counted = db_profile.wrap_connection(connection)

    with db_profile.scope("batch"):
        with db_profile.scope("hand"):
            counted.cursor().execute("SELECT 1")
            counted.cursor().execute("SELECT 2")
        with db_profile.scope("hand"):
            counted.cursor().execute("SELECT 3")

    assert on.by_scope["batch"].queries == 3
    assert on.by_scope["batch"].entries == 1
    assert on.by_scope["hand"].queries == 3
    assert on.by_scope["hand"].entries == 2
    assert on.by_scope["hand"].queries_per_entry == 1.5


def test_a_scope_inside_itself_counts_a_statement_once(on, connection) -> None:
    """Otherwise a recursive path would report round trips it never made."""
    counted = db_profile.wrap_connection(connection)

    with db_profile.scope("refresh"), db_profile.scope("refresh"):
        counted.cursor().execute("SELECT 1")

    assert on.by_scope["refresh"].queries == 1


def test_the_decorator_attributes_a_whole_method(on, connection) -> None:
    counted = db_profile.wrap_connection(connection)

    @db_profile.scoped("secondary_refresh")
    def refresh_one_table() -> None:
        counted.cursor().execute("SELECT 1")
        counted.cursor().execute("SELECT 2")

    refresh_one_table()
    refresh_one_table()

    assert on.by_scope["secondary_refresh"].entries == 2
    assert on.by_scope["secondary_refresh"].queries_per_entry == 2.0


def test_the_decorator_keeps_the_method_it_wraps(on) -> None:
    @db_profile.scoped("whatever")
    def named(a, b=2):
        """Doc."""
        return a + b

    assert named.__name__ == "named"
    assert named(1, b=3) == 4


def test_scopes_are_per_thread(on, connection) -> None:
    """An importer thread must not land its statements in the HUD's scope."""
    import threading

    counted = db_profile.wrap_connection(connection)
    started = threading.Event()

    def other_thread() -> None:
        started.wait()
        # No scope open on this thread.
        sqlite3.connect(":memory:").close()
        db_profile.get_profile().record("SELECT 'other'", 0.0)

    worker = threading.Thread(target=other_thread)
    worker.start()
    with db_profile.scope("hand"):
        started.set()
        worker.join()
        counted.cursor().execute("SELECT 1")

    assert on.by_scope["hand"].queries == 1
    assert on.total.calls == 2


# -- naming and reporting -------------------------------------------------


def test_statements_are_named_after_the_sql_catalogue(on, connection) -> None:
    catalogue = {"get_hand_1day_ago": "SELECT max(id)\n  FROM Hands\n WHERE startTime < ?"}
    counted = db_profile.wrap_connection(connection, catalogue)

    with pytest.raises(sqlite3.OperationalError):
        # Naming must not depend on the statement succeeding.
        counted.cursor().execute("SELECT max(id) FROM Hands WHERE startTime < ?", (1,))

    assert "get_hand_1day_ago" in on.by_statement
    assert on.by_statement["get_hand_1day_ago"].calls == 1


def test_a_query_with_injected_columns_keeps_its_name(on, connection) -> None:
    """The HUD aggregate has columns injected before it runs; it is the one
    statement whose name matters most, and an exact match would lose it."""
    catalogue = {
        "get_stats_from_hand_aggregated": (
            "/* explain query plan */ SELECT hp.playerId, count(1) AS n, sum(hp.street0VPI) AS vpip FROM HandsPlayers hp"
        ),
    }
    counted = db_profile.wrap_connection(connection, catalogue)

    with pytest.raises(sqlite3.OperationalError):
        counted.cursor().execute(
            "/* explain query plan */ SELECT hp.playerId, count(1) AS n, "
            "sum(hp.chipEvBtn) AS ev_btn, sum(hp.street0VPI) AS vpip FROM HandsPlayers hp",
        )

    assert "get_stats_from_hand_aggregated (assembled)" in on.by_statement


def test_an_ambiguous_opening_is_not_used_to_name_anything(on, connection) -> None:
    """Two catalogue entries sharing an opening must not be confused."""
    shared = "SELECT playerId, count(1), sum(street0VPI), sum(street0Aggr) FROM HandsPlayers WHERE "
    counted = db_profile.wrap_connection(connection, {"query_a": shared + "a = 1", "query_b": shared + "b = 2"})

    with pytest.raises(sqlite3.OperationalError):
        counted.cursor().execute(shared + "c = 3")

    assert not any("assembled" in label for label in on.by_statement)


def test_an_unknown_statement_is_named_by_its_text(on, connection) -> None:
    counted = db_profile.wrap_connection(connection, {})

    counted.cursor().execute("SELECT name FROM t")

    assert "select name from t" in on.by_statement


def test_the_report_names_the_repeat_offenders(on, connection) -> None:
    counted = db_profile.wrap_connection(connection, {"cheap_lookup": "SELECT 1"})

    with db_profile.scope("hand"):
        for _ in range(12):
            counted.cursor().execute("SELECT 1")

    report = on.report()
    assert "cheap_lookup" in report
    assert "12" in report
    assert "hand" in report


def test_an_empty_report_says_so(on) -> None:
    assert "none recorded" in on.report()


def test_the_delta_reporter_stays_quiet_until_something_changes(on, connection) -> None:
    counted = db_profile.wrap_connection(connection)
    reporter = db_profile.DeltaReporter("profile:", on)

    assert reporter.maybe_log() is False

    counted.cursor().execute("SELECT 1")
    assert reporter.maybe_log() is True
    assert reporter.maybe_log() is False


def test_the_delta_reporter_is_silent_when_profiling_is_off(monkeypatch, connection) -> None:
    monkeypatch.delenv(db_profile.ENV_FLAG, raising=False)
    profile = db_profile.QueryProfile()
    profile.record("SELECT 1", 0.0)

    assert db_profile.DeltaReporter("profile:", profile).maybe_log() is False


# -- end to end -----------------------------------------------------------


def test_a_real_database_counts_and_names_its_own_statements(monkeypatch, legacy_config) -> None:
    """The wiring in Database.connect, against a real schema."""
    monkeypatch.setenv(db_profile.ENV_FLAG, "1")
    profile = db_profile.get_profile()
    profile.reset()

    from fpdb_3_legacy.Database import Database

    db = Database(legacy_config)
    try:
        db.recreate_tables()
        profile.reset()
        with db_profile.scope("hand"):
            db.get_table_info("1")
        # Read before the teardown below resets the counters.
        calls = profile.total.calls
        hand_queries = profile.by_scope["hand"].queries
        named = "get_table_name" in profile.by_statement
    finally:
        db.disconnect()
        profile.reset()

    assert calls >= 1, "statements through a real Database must be counted"
    assert hand_queries == calls, "and attributed to the scope that asked for them"
    assert named, "and named after the SQL catalogue entry they came from"
