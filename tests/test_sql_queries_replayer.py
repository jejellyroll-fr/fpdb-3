"""Regression tests for hand-range and replayer queries."""

from fpdb_3_legacy.SQL import Sql
from fpdb_3_legacy.sql_queries_replayer import replayer_queries


def test_replayer_queries_are_installed_with_sqlite_placeholders() -> None:
    expected = replayer_queries()
    assert len(expected) == 10
    for backend in ("mysql", "postgresql"):
        assert expected.items() <= Sql(db_server=backend).query.items()
    sqlite_expected = {key: value.replace("%s", "?") for key, value in expected.items()}
    assert sqlite_expected.items() <= Sql(db_server="sqlite").query.items()


def test_replayer_queries_keep_board_player_and_action_context() -> None:
    queries = replayer_queries()

    assert "join HandsPlayers" in queries["handsInRange"]
    assert "h.startTime <datetest>" in queries["handsInRangeSession"]
    assert "<position_test>" in queries["handsInRangeSessionFilter"]
    # The tournament viewer filters on its tournaments' types (#650).
    assert "left join TourneyTypes tt" in queries["tourneyHandsInRangeSessionFilter"]
    assert "Boards" in queries["singleHandBoards"]
    assert "HandsPlayers" in queries["playerHand"]
    actions = queries["handActions"]
    assert "HandsActions" in actions
    assert "Actions" in actions
    assert "ha.id ASC" in actions
    # The Hand Viewer search matches a room hand number or an fpdb id.
    assert "siteHandNo = %s OR id = %s" in queries["handsMatchingNumber"]
