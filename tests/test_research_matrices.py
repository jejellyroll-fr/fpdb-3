"""Qt-free semantics for position matrices and board heatmaps (#363)."""

from __future__ import annotations

from types import SimpleNamespace

from fpdb_3_legacy.analytics_query import QueryRow
from fpdb_3_legacy.research_matrices import build_matrix


def result(metric: str, rows: list[QueryRow]) -> SimpleNamespace:
    return SimpleNamespace(rows=rows, compiled=SimpleNamespace(metric=metric))


def test_position_matrix_keeps_axes_and_empty_matchups_addressable() -> None:
    matrix = build_matrix(
        result(
            "opportunities",
            [
                QueryRow({"position": 0, "opponent_position": 1}, 12, 12, 12, "count"),
                QueryRow({"position": 1, "opponent_position": 0}, 4, 4, 4, "count"),
            ],
        ),
        ("position", "opponent_position"),
        min_sample=10,
    )

    assert matrix.rows[:2] == (0, 1)
    assert matrix.columns[:2] == (0, 1)
    assert matrix.cell(0, 1).row_label == "BTN"
    assert matrix.cell(0, 1).column_label == "CO"
    assert matrix.cell(0, 1).opportunities == 12
    assert matrix.cell(1, 1).opportunities == 0
    assert not matrix.cell(1, 1).sample_sufficient
    assert len(matrix.low_sample_cells) == 1


def test_board_matrix_uses_canonical_texture_order_and_keeps_unknown() -> None:
    matrix = build_matrix(
        result(
            "bet_frequency",
            [
                QueryRow({"board_suit": "rainbow", "board_pairing": "unpaired"}, 20, 13, 13, "bp", 6500),
                QueryRow({"board_suit": None, "board_pairing": "paired"}, 2, 1, 1, "bp", 5000),
            ],
        ),
        ("board_suit", "board_pairing"),
        min_sample=10,
    )

    assert matrix.rows[0] == "rainbow"
    assert matrix.rows[-1] is None
    assert matrix.columns[0] == "unpaired"
    assert matrix.cell("rainbow", "unpaired").metric_label == "65.0%"
    assert matrix.cell(None, "paired").row_label == "Unknown / unclassified"
    assert matrix.cell(None, "paired").opportunities == 2
    assert matrix.cell(None, "paired") in matrix.low_sample_cells


def test_unknown_values_are_not_redistributed_into_known_cells() -> None:
    matrix = build_matrix(
        result(
            "opportunities",
            [QueryRow({"board_suit": "rainbow", "board_pairing": None}, 3, 3, 3, "count")],
        ),
        ("board_suit", "board_pairing"),
    )

    assert matrix.cell("rainbow", None).opportunities == 3
    assert matrix.cell("rainbow", "unpaired").opportunities == 0
    assert matrix.has_unknown


def test_stack_depth_matrix_uses_canonical_depth_order() -> None:
    matrix = build_matrix(
        result(
            "opportunities",
            [
                QueryRow({"effective_stack_bucket": "100_plus", "position": 0}, 1, 1, 1, "count"),
                QueryRow({"effective_stack_bucket": "under_10", "position": 0}, 1, 1, 1, "count"),
                QueryRow({"effective_stack_bucket": "10_to_15", "position": 0}, 1, 1, 1, "count"),
            ],
        ),
        ("effective_stack_bucket", "position"),
    )

    assert matrix.rows[:2] == ("under_10", "10_to_15")
    assert matrix.rows.index("100_plus") < matrix.rows.index("unknown")
    assert matrix.rows.index("10_to_15") < matrix.rows.index("100_plus")
