"""Regression tests for secondary hand artifact queries."""

from fpdb_3_legacy.SQL import Sql
from fpdb_3_legacy.sql_queries_hand_artifacts import hand_artifact_queries


def test_hand_artifact_queries_are_installed_with_sqlite_placeholders() -> None:
    expected = hand_artifact_queries()
    assert len(expected) == 6
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
