"""Regression tests for tournament persistence queries."""

from fpdb_3_legacy.SQL import Sql
from fpdb_3_legacy.sql_queries_tournament_persistence import tournament_persistence_queries


def test_tournament_persistence_queries_are_installed_with_sqlite_placeholders() -> None:
    expected = tournament_persistence_queries()
    assert len(expected) == 18
    for backend in ("mysql", "postgresql"):
        assert expected.items() <= Sql(db_server=backend).query.items()
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
