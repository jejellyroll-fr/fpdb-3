"""Regression tests for SQL utility queries."""

from fpdb_3_legacy.SQL import Sql
from fpdb_3_legacy.sql_queries_utility import utility_queries


def test_utility_queries_are_installed_with_sqlite_placeholders() -> None:
    expected = utility_queries()
    assert len(expected) == 21
    for backend in ("mysql", "postgresql"):
        assert expected.items() <= Sql(db_server=backend).query.items()
    sqlite_expected = {key: value.replace("%s", "?") for key, value in expected.items()}
    assert sqlite_expected.items() <= Sql(db_server="sqlite").query.items()


def test_utility_queries_keep_player_and_count_contracts() -> None:
    queries = utility_queries()

    assert "commentTs=CURRENT_TIMESTAMP" in queries["update_player_comment"]
    assert queries["get_player_name"] == "SELECT name FROM Players WHERE id=%s"
    assert queries["getHandCount"] == "SELECT COUNT(*) FROM Hands"
    assert queries["getTourneyCount"] == "SELECT COUNT(*) FROM Tourneys"
    assert queries["getTourneyTypeCount"] == "SELECT COUNT(*) FROM TourneyTypes"


def test_utility_queries_keep_dump_catalogue() -> None:
    queries = utility_queries()
    tables = (
        "Autorates",
        "Backings",
        "Gametypes",
        "Hands",
        "HandsActions",
        "HandsPlayers",
        "HudCache",
        "Players",
        "RawHands",
        "RawTourneys",
        "Settings",
        "Sites",
        "TourneyTypes",
        "Tourneys",
        "TourneysPlayers",
    )
    for table in tables:
        assert queries["get" + table] == "SELECT * FROM " + table
