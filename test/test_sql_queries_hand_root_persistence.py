"""Regression tests for the root hand persistence query."""

from fpdb_3_legacy.SQL import Sql
from fpdb_3_legacy.sql_queries_hand_root_persistence import hand_root_persistence_queries


def test_hand_root_persistence_query_is_installed_with_sqlite_placeholders() -> None:
    expected = hand_root_persistence_queries()
    assert set(expected) == {"store_hand"}
    for backend in ("mysql", "postgresql"):
        assert expected.items() <= Sql(db_server=backend).query.items()
    sqlite_expected = {key: value.replace("%s", "?") for key, value in expected.items()}
    assert sqlite_expected.items() <= Sql(db_server="sqlite").query.items()


def test_hand_root_persistence_keeps_column_and_placeholder_alignment() -> None:
    store = hand_root_persistence_queries()["store_hand"]

    assert store.count("%s") == 36
    for ordered_columns in (
        ("tablename", "sitehandno", "tourneyId", "gametypeid", "sessionId", "fileId"),
        ("boardcard1", "boardcard2", "boardcard3", "boardcard4", "boardcard5", "runItTwice"),
        ("street0Pot", "street1Pot", "street2Pot", "street3Pot", "street4Pot", "finalPot", "bombPot"),
    ):
        indexes = [store.index(column) for column in ordered_columns]
        assert indexes == sorted(indexes)
    assert store.index("heroSeat") < store.index("maxPosition") < store.index("texture")
