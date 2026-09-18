"""Regression tests for auxiliary hand and import-file queries."""

from fpdb_3_legacy.board_features import BOARD_FEATURE_COLUMNS
from fpdb_3_legacy.SQL import Sql
from fpdb_3_legacy.sql_queries_import_auxiliary import import_auxiliary_queries


def test_import_auxiliary_queries_are_installed_with_sqlite_placeholders() -> None:
    expected = import_auxiliary_queries()
    assert len(expected) == 6
    for backend in ("mysql", "postgresql"):
        assert expected.items() <= Sql(db_server=backend).query.items()
    sqlite_expected = {key: value.replace("%s", "?") for key, value in expected.items()}
    assert sqlite_expected.items() <= Sql(db_server="sqlite").query.items()


def test_import_auxiliary_queries_keep_board_and_pot_dimensions() -> None:
    queries = import_auxiliary_queries()
    board = queries["store_boards"]
    pot = queries["store_hands_pots"]

    assert board.index("handId") < board.index("boardId") < board.index("boardcard1") < board.index("boardcard5")
    for column in ("handId", "potId", "boardId", "hiLo", "playerId", "pot", "collected", "rake"):
        assert column in pot


def test_board_feature_insert_carries_the_classified_columns() -> None:
    features = import_auxiliary_queries()["store_board_features"]
    # One row per board and street (#295): which hand, which run, which street,
    # and the classification of the cards visible entering it.
    for column in BOARD_FEATURE_COLUMNS:
        assert column in features
    assert features.index("handId") < features.index("streetName") < features.index("textureMask")
    assert features.count("%s") == len(BOARD_FEATURE_COLUMNS) + 1


def test_import_auxiliary_queries_keep_file_counters() -> None:
    queries = import_auxiliary_queries()

    for column in ("hands", "storedHands", "dups", "partial", "skipped", "errs", "ttime100", "finished"):
        assert column in queries["store_file"]
        assert column in queries["update_file"]
    assert "WHERE file=%s" in queries["get_id"]
    assert queries["update_file"].rstrip().endswith("WHERE id=%s")
