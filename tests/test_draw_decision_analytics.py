"""Decision counts for draw rounds, from the canonical imported action rows."""

from __future__ import annotations

from pathlib import Path

from fpdb_3_legacy import analytics_definitions
from fpdb_3_legacy.analytics_query import Query, run_query

FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "hands"
    / "pokerstars"
    / "draw"
    / "triple_draw.txt"
)
MERGE_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "regression-test-files"
    / "cash"
    / "Merge"
    / "Draw"
    / "3-Draw-Limit-USD-1-2-201104.Sample.with.showdown.txt"
)


def test_draw_counts_only_players_who_reached_each_decision(importer, fresh_db) -> None:
    importer.addImportFile(str(FIXTURE), "PokerStars")
    stored, *_ = importer.runImport()
    assert stored == 1

    def distribution(draw_number: int) -> dict[int | None, int]:
        result = run_query(
            fresh_db,
            Query(
                metric="opportunities",
                filters={
                    "draw_number": [draw_number, draw_number],
                    "action_taken": ["discards", "stands pat"],
                },
                group_by=("cards_drawn",),
            ),
        )
        return {row.group["cards_drawn"]: row.opportunities for row in result.rows}

    # Hero folded before the first draw; rumble1111 folded after it. Neither
    # creates a phantom opportunity in a draw they never reached.
    assert distribution(1) == {1: 1, 2: 2}
    assert distribution(2) == {0: 1, 1: 1}
    assert distribution(3) == {0: 2}


def test_builtin_draw_definitions_run_on_the_imported_draw_hand(importer, fresh_db) -> None:
    importer.addImportFile(str(FIXTURE), "PokerStars")
    stored, *_ = importer.runImport()
    assert stored == 1

    definition = analytics_definitions.load_default_registry().resolve("draw_decision_distribution")
    result = analytics_definitions.run_definition(fresh_db, definition)
    grouped = {
        (row.group["draw_number"], row.group["cards_drawn"]): row.opportunities
        for row in result.rows
    }
    assert grouped == {
        (1, 1): 1,
        (1, 2): 2,
        (2, 0): 1,
        (2, 1): 1,
        (3, 0): 2,
    }


def test_draw_definition_excludes_non_draw_discard_actions(importer, fresh_db) -> None:
    importer.addImportFile(str(FIXTURE), "PokerStars")
    stored, *_ = importer.runImport()
    assert stored == 1

    # Irish Poker is stored as base="hold" even though its mandatory turn
    # discard is represented by the same action type as a draw decision.
    cursor = fresh_db.get_cursor()
    cursor.execute("UPDATE Gametypes SET base = 'hold'")

    definition = analytics_definitions.load_default_registry().resolve("draw_decision_distribution")
    result = analytics_definitions.run_definition(fresh_db, definition)
    assert result.rows == []

    # The reusable dimensions also refuse to label non-draw actions with a
    # draw number or card count when a caller omits the built-in definition.
    unscoped = run_query(
        fresh_db,
        Query(
            metric="opportunities",
            filters={"action_taken": ["discards", "stands pat"]},
            group_by=("draw_number", "cards_drawn"),
        ),
    )
    assert {
        (row.group["draw_number"], row.group["cards_drawn"]): row.opportunities
        for row in unscoped.rows
    } == {(None, None): 7}


def test_merge_zero_discard_events_are_stand_pat_decisions(importer, fresh_db) -> None:
    importer.addImportFile(str(MERGE_FIXTURE), "Merge")
    stored, *_ = importer.runImport()
    assert stored == 1

    result = run_query(
        fresh_db,
        Query(
            metric="opportunities",
            filters={"action_taken": ["discards", "stands pat"]},
            group_by=("draw_number", "cards_drawn"),
        ),
    )
    grouped = {
        (row.group["draw_number"], row.group["cards_drawn"]): row.opportunities
        for row in result.rows
    }
    assert grouped == {
        (1, 1): 1,
        (1, 2): 1,
        (2, 0): 1,
        (2, 1): 1,
        (3, 0): 2,
    }

    cursor = fresh_db.get_cursor()
    cursor.execute(
        "SELECT handId, actionNo FROM HandsActions "
        "WHERE actionType = 'discards' AND numDiscarded = 1 LIMIT 1",
    )
    hand_id, action_no = cursor.fetchone()
    cursor.execute(
        "UPDATE HandsActions SET numDiscarded = -1 WHERE handId = ? AND actionNo = ?",
        (hand_id, action_no),
    )
    unknown = run_query(
        fresh_db,
        Query(
            metric="opportunities",
            filters={"action_taken": ["discards", "stands pat"]},
            group_by=("draw_number", "cards_drawn"),
        ),
    )
    assert {
        (row.group["draw_number"], row.group["cards_drawn"]): row.opportunities
        for row in unknown.rows
    } == {
        (1, 2): 1,
        (1, None): 1,
        (2, 0): 1,
        (2, 1): 1,
        (3, 0): 2,
    }
