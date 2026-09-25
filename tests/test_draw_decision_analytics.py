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
