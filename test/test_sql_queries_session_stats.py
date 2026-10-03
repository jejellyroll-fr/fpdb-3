"""Regression tests for session profit timeline queries."""

from fpdb_3_legacy.SQL import Sql
from fpdb_3_legacy.sql_queries_session_stats import session_stats_queries
from fpdb_3_legacy.sql_query_placeholders import finalize_query_placeholders


def test_session_stats_query_is_installed_exactly() -> None:
    for backend in ("mysql", "postgresql", "sqlite"):
        expected = session_stats_queries(backend)
        assert expected.keys() == {"sessionStats", "sessionGuardHands"}
        # As the catalogue installs them: SQLite's bind markers normalized.
        installed = finalize_query_placeholders(dict(expected), backend)
        installed.pop("placeholder")
        assert installed.items() <= Sql(db_server=backend).query.items()


def test_session_stats_keeps_backend_time_and_dynamic_filters() -> None:
    mysql = session_stats_queries("mysql")["sessionStats"]
    postgresql = session_stats_queries("postgresql")["sessionStats"]
    sqlite = session_stats_queries("sqlite")["sessionStats"]

    assert "UNIX_TIMESTAMP(h.startTime)" in mysql
    assert "EXTRACT(epoch from h.startTime)" in postgresql
    assert "STRFTIME('<ampersand_s>', h.startTime)" in sqlite
    for query in (mysql, postgresql, sqlite):
        assert "h.id" in query
        assert "hp.totalProfit" in query
        assert "hp.allInEV" in query
        assert "gt.bigBlind" in query
        assert "gt.currency" in query
        assert "ORDER by time, h.id" in query
        assert "<player_test>" in query
        assert "<datestest>" in query
        assert "<limit_test>" in query
        assert "<seats_test>" in query
        assert "<currency_test>" in query


def test_session_guard_query_reads_the_same_rows_with_parameters_only() -> None:
    """The Session Guard (#395) reads the Session Viewer's columns, ring games only.

    Its filters are bound parameters -- one hero id, one start-time cut-off -- and the text
    is fixed: no template marker is left to fill in at run time.
    """
    for backend, placeholder in (("mysql", "%s"), ("postgresql", "%s"), ("sqlite", "?")):
        guard = Sql(db_server=backend).query["sessionGuardHands"]
        for column in ("h.id", "hp.totalProfit", "hp.allInEV", "gt.bigBlind", "gt.currency"):
            assert column in guard
        assert f"hp.playerId = {placeholder}" in guard
        assert f"h.startTime >= {placeholder}" in guard
        assert "ring" in guard
        assert "<" not in guard
        assert guard.count(placeholder) == 2
        assert "ORDER by time, h.id" in guard


def test_session_guard_query_reads_epoch_seconds_from_sqlite(tmp_path) -> None:
    import sqlite3

    query = Sql(db_server="sqlite").query["sessionGuardHands"]
    connection = sqlite3.connect(str(tmp_path / "guard.sqlite3"))
    connection.executescript(
        """
        CREATE TABLE Hands (id INTEGER, startTime TEXT, gametypeId INTEGER);
        CREATE TABLE HandsPlayers (handId INTEGER, playerId INTEGER, totalProfit INTEGER, allInEV INTEGER);
        CREATE TABLE Gametypes (Id INTEGER, type TEXT, bigBlind INTEGER, currency TEXT);
        INSERT INTO Gametypes VALUES (1, 'ring', 100, 'USD'), (2, 'tour', 100, 'T$');
        INSERT INTO Hands VALUES (1, '2026-10-03 12:00:00', 1), (2, '2026-10-03 12:30:15', 1),
                                 (3, '2026-10-03 12:31:00', 2), (4, '2026-10-02 08:00:00', 1);
        INSERT INTO HandsPlayers VALUES (1, 7, -150, -150), (2, 7, 300, 250), (3, 7, 50, 50),
                                        (4, 7, 10, 10), (2, 8, -300, -250);
        """
    )

    rows = connection.execute(query, (7, "2026-10-03 00:00:00")).fetchall()

    # Ring hands of player 7 since the cut-off, in order, with UTC epoch seconds.
    assert rows == [(1, 1791028800, -150, -150, 100, "USD"), (2, 1791030615, 300, 250, 100, "USD")]
