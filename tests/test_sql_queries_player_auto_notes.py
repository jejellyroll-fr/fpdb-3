"""Regression tests for player automatic-note queries."""

from fpdb_3_legacy.SQL import Sql
from fpdb_3_legacy.sql_queries_player_auto_notes import player_auto_note_queries


def test_player_auto_note_queries_are_installed_with_sqlite_placeholders() -> None:
    expected = player_auto_note_queries()
    assert len(expected) == 10
    for backend in ("mysql", "postgresql"):
        assert expected.items() <= Sql(db_server=backend).query.items()
    sqlite_expected = {key: value.replace("%s", "?") for key, value in expected.items()}
    assert sqlite_expected.items() <= Sql(db_server="sqlite").query.items()


def test_player_auto_notes_keep_rule_identity_and_upsert_contract() -> None:
    queries = player_auto_note_queries()

    find = queries["find_player_auto_note"]
    for condition in ("playerId=%s", "handId=%s", "ruleId=%s", "ruleVersion=%s"):
        assert condition in find
    store = queries["store_player_auto_note"]
    assert store.index("ruleId") < store.index("ruleVersion") < store.index("noteText") < store.index("evidence")
    assert "updatedTs=CURRENT_TIMESTAMP" in queries["update_player_auto_note"]


def test_player_auto_note_reports_keep_dynamic_filter_hook() -> None:
    queries = player_auto_note_queries()

    for key in ("get_recent_player_auto_notes", "get_auto_note_player_summary", "get_auto_note_rule_summary"):
        assert "/*AUTONOTE_FILTERS*/" in queries[key]
    assert "order by pan.createdTs desc, pan.id desc" in queries["get_recent_player_auto_notes"]
    assert "comment is not null and comment <> ''" in queries["player_has_any_notes"]
    assert "from PlayerAutoNotes" in queries["player_has_any_notes"]
