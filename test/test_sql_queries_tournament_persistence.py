"""Regression tests for tournament persistence queries."""

from fpdb_3_legacy.SQL import Sql
from fpdb_3_legacy.sql_queries_tournament_persistence import tournament_persistence_queries


def test_tournament_persistence_queries_are_installed_with_sqlite_placeholders() -> None:
    for backend in ("mysql", "postgresql"):
        expected = tournament_persistence_queries(backend)
        assert len(expected) == 18
        assert expected.items() <= Sql(db_server=backend).query.items()
    expected = tournament_persistence_queries("sqlite")
    sqlite_expected = {key: value.replace("%s", "?") for key, value in expected.items()}
    assert sqlite_expected.items() <= Sql(db_server="sqlite").query.items()


def test_tournament_persistence_keeps_results_and_bounties() -> None:
    queries = tournament_persistence_queries()

    for column in ("rank", "winnings", "winningsCurrency", "rebuyCount", "addOnCount", "koCount"):
        assert column in queries["updateTourneysPlayer"]
        assert column in queries["insertTourneysPlayer"]
    assert "koCount = case when koCount is null" in queries["updateTourneysPlayerBounties"]
    assert "CASE WHEN %s IS NULL THEN rank ELSE %s END" in queries["updateTourneysPlayerResults"]


def test_tournament_persistence_keeps_hand_player_type_repair() -> None:
    queries = tournament_persistence_queries()

    assert "tourneyTypeId <> %s" in queries["selectHandsPlayersWithWrongTTypeId"]
    assert "SET tourneyTypeId= %s" in queries["updateHandsPlayersForTTypeId"]
    assert queries["handsPlayersTTypeId_joiner"] == " OR TourneysPlayersId+0="
    assert queries["handsPlayersTTypeId_joiner_id"] == " OR id="


def test_mysql_quotes_reserved_tournament_rank_column() -> None:
    queries = tournament_persistence_queries("mysql")
    assert "SET `rank` = %s" in queries["updateTourneysPlayer"]
    assert "SET `rank` = CASE" in queries["updateTourneysPlayerResults"]
    assert "`rank`," in queries["insertTourneysPlayer"]
