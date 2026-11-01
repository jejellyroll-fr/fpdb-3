"""Regression tests for the full-width HandsPlayers persistence query."""

from fpdb_3_legacy.SQL import Sql
from fpdb_3_legacy.sql_queries_hand_player_persistence import hand_player_persistence_queries


def test_hand_player_persistence_query_is_installed_with_sqlite_placeholders() -> None:
    expected = hand_player_persistence_queries()
    assert set(expected) == {"store_hands_players"}
    for backend in ("mysql", "postgresql"):
        assert expected.items() <= Sql(db_server=backend).query.items()
    sqlite_expected = {key: value.replace("%s", "?") for key, value in expected.items()}
    assert sqlite_expected.items() <= Sql(db_server="sqlite").query.items()


def test_hand_player_persistence_keeps_modern_stat_and_result_columns() -> None:
    store = hand_player_persistence_queries()["store_hands_players"]

    for column in (
        "allInEV",
        "street2DelayedCBChance",
        "street2DelayedCBDone",
        "street2ProbeChance",
        "street2ProbeDone",
        "isCashOut",
        "cashOutFee",
    ):
        assert column in store
    assert store.index("cashOutFee") < store.index("isCashOut")
