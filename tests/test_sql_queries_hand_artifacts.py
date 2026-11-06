"""Regression tests for secondary hand artifact queries."""

from unittest.mock import MagicMock

from fpdb_3_legacy.Database import Database
from fpdb_3_legacy.SQL import Sql
from fpdb_3_legacy.sql_queries_hand_artifacts import hand_artifact_queries


def test_hand_artifact_queries_are_installed_with_sqlite_placeholders() -> None:
    expected = hand_artifact_queries()
    assert len(expected) == 7
    for backend in ("mysql", "postgresql"):
        assert expected.items() <= Sql(db_server=backend).query.items()
    sqlite_expected = {key: value.replace("%s", "?") for key, value in expected.items()}
    assert sqlite_expected.items() <= Sql(db_server="sqlite").query.items()


def test_hand_artifacts_keep_action_and_stove_dimensions() -> None:
    queries = hand_artifact_queries()

    for column in ("actionNo", "streetActionNo", "raiseTo", "amountCalled", "cardsDiscarded", "allIn"):
        assert column in queries["store_hands_actions"]
    for column in ("streetId", "boardId", "hiLo", "rankId", "value", "cards", "ev"):
        assert column in queries["store_hands_stove"]


def test_hand_artifacts_keep_cashout_column_order() -> None:
    queries = hand_artifact_queries()
    cashout = queries["store_hands_cashout"]

    assert cashout.index("handId") < cashout.index("playerId") < cashout.index("amount") < cashout.index("fee")
    assert "select p.name, hc.amount, hc.fee" in queries["get_hands_cashout"]
    assert "select p.name, hs.combo, hs.cards" in queries["get_hands_showdown"]
    assert "select p.name, hp.splashWinnings" in queries["get_hands_splash"]


def test_a_failed_legacy_splash_read_clears_an_aborted_transaction() -> None:
    cursor = MagicMock()
    cursor.execute.side_effect = RuntimeError("splashWinnings is absent")
    db = object.__new__(Database)
    db.sql = MagicMock()
    db.sql.query = {"get_hands_splash": "select"}
    db.get_cursor = MagicMock(return_value=cursor)
    db._rollback_after_failed_read = MagicMock()

    assert db.get_hands_splash(7) == {}
    db._rollback_after_failed_read.assert_called_once_with()
