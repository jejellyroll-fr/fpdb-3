"""The four ways the Research Browser answered wrongly or unreadably (#355).

Reported by a user who could not tell whether the tool was broken or whether
they were holding it wrong. It was the tool, four times over:

* a third of the shipped presets filtered on an *opportunity* situation and
  measured the action that leaves it, so they could only ever answer 0%;
* the game, limit, room and currency filters were closed domains offered as
  empty text boxes;
* nothing said when one number averaged two games and two limits;
* seats printed as ``-2, -1, 0`` while the pane's own filter called them
  BB, SB, BTN.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from fpdb_3_legacy import research_browser as rb
from fpdb_3_legacy.research_labels import is_expert_only

ROOT = Path(__file__).parents[1]
PRESET_LIBRARY = ROOT / "fpdb_3_legacy" / "research_presets.d" / "nlhe_6max.json"

#: Metrics that count an action which *changes* a decision's most specific
#: situation label.
ACTION_METRICS = frozenset({"raise_frequency", "bet_frequency"})


def _shipped_presets() -> list[dict[str, Any]]:
    def walk(node):
        if isinstance(node, dict):
            if "name" in node and "metric" in node:
                yield node
            for value in node.values():
                yield from walk(value)
        elif isinstance(node, list):
            for value in node:
                yield from walk(value)

    return list(walk(json.loads(PRESET_LIBRARY.read_text())))


# --- 1. presets that could only answer zero ---------------------------------


def test_no_shipped_preset_measures_an_action_out_of_a_spot_the_action_leaves() -> None:
    """The mistake that made 16 of 46 presets structurally empty.

    ``primary_situation`` is the most specific label a decision matched, so
    raising against an open relabels it ``three_bet`` and takes it out of
    ``facing_open``. A preset filtering the opportunity and counting the action
    therefore excludes exactly what it counts: 0/1812 on the database this was
    reported from, while 82 three-bets sat in the same table.
    """
    offenders = [
        preset["id"]
        for preset in _shipped_presets()
        if isinstance((preset.get("filters") or {}).get("primary_situation"), str)
        and preset.get("metric") in ACTION_METRICS
    ]

    assert not offenders, (
        f"{len(offenders)} preset(s) filter primary_situation and measure an action that leaves it: "
        f"{offenders}. Use the 'situation' filter, which keeps the decision among the opportunities."
    )


def test_the_repointed_presets_kept_the_spot_they_were_asking_about() -> None:
    # The fix is the column, not the question: every one of them still names
    # its own opportunity.
    by_id = {preset["id"]: preset for preset in _shipped_presets()}

    assert by_id["three_bet_by_position"]["filters"]["situation"] == "facing_open"
    assert by_id["flop_cbet_frequency"]["filters"]["situation"] == "cbet_spot"
    assert by_id["four_bet_by_position"]["filters"]["situation"] == "facing_3bet"
    assert "primary_situation" not in by_id["three_bet_by_position"]["filters"]


def test_the_opportunity_filter_is_offered_to_beginners() -> None:
    """Hiding it is what left the right question unaskable.

    Every repointed preset uses ``situation``; behind Expert mode, loading one
    would show a beginner a filter they cannot see in the picker or change.
    """
    assert not is_expert_only("situation")
    assert rb.filter_spec("situation").choices, "a closed domain deserves its picker"


# --- 2. closed domains offered as free text ---------------------------------


class _Cursor:
    def __init__(self, rows: list[tuple]) -> None:
        self._rows = rows
        self.statements: list[str] = []

    def execute(self, sql: str, params: Any = ()) -> None:
        self.statements.append(sql)

    def fetchall(self) -> list[tuple]:
        return self._rows


class _Db:
    def __init__(self, rows: list[tuple]) -> None:
        self.cursor = _Cursor(rows)

    def get_cursor(self, *args: Any, **kwargs: Any) -> _Cursor:
        return self.cursor


@pytest.mark.parametrize("name", sorted(rb.DATABASE_CHOICES))
def test_a_closed_domain_lists_only_what_was_played(name: str) -> None:
    """Sites holds every room fpdb can parse -- about a hundred and thirty.

    Listing the reference table offered a user every room in the world instead
    of the one they play, which is not an improvement on a text box.
    """
    assert "JOIN Hands" in rb.DATABASE_CHOICES[name], name


def test_the_values_come_back_as_a_reader_would_say_them() -> None:
    db = _Db([("omahahi",), ("holdem",)])

    choices = rb.database_choices(db, "game")

    assert [(choice.value, choice.label) for choice in choices] == [
        ("omahahi", "Omaha"),
        ("holdem", "Hold'em"),
    ]


def test_a_domain_that_cannot_be_listed_leaves_the_filter_usable() -> None:
    # Free text is a fallback, not a failure: a picker must never cost the pane.
    db = MagicMock(name="db")
    db.get_cursor.side_effect = RuntimeError("no such table")

    assert rb.database_choices(db, "game") == ()
    assert rb.spec_for_database(db, "game") == rb.filter_spec("game")


def test_a_filter_that_already_has_choices_is_left_alone() -> None:
    db = _Db([("nonsense",)])

    assert rb.spec_for_database(db, "primary_situation").choices == rb.filter_spec("primary_situation").choices


def test_the_form_opens_with_the_filters_that_keep_a_number_meaningful() -> None:
    from fpdb_3_legacy.GuiResearchBrowser import _DEFAULT_FILTERS

    assert "game" in _DEFAULT_FILTERS
    assert "limit" in _DEFAULT_FILTERS
    assert "hero" in _DEFAULT_FILTERS


# --- 3. one number over two populations -------------------------------------


def test_a_mixed_population_is_named_not_merely_flagged() -> None:
    scope = rb.PopulationScope(games=("holdem", "omahahi"), limits=("nl", "pl"), sites=("Winamax",))

    warning = scope.describe()

    assert scope.is_mixed
    assert "Hold'em" in warning and "Omaha" in warning
    assert "no limit" in warning and "pot limit" in warning
    assert "Winamax" not in warning, "one room is not a mixture"


def test_a_single_population_says_nothing() -> None:
    scope = rb.PopulationScope(games=("holdem",), limits=("nl",), sites=("Winamax",))

    assert not scope.is_mixed
    assert scope.describe() == ""


def test_a_scope_that_cannot_be_read_annotates_nothing() -> None:
    db = MagicMock(name="db")
    db.get_cursor.side_effect = RuntimeError("gone")

    scope = rb.population_scope(db, rb.preset_to_query({"metric": "fold_frequency", "filters": {}, "group_by": []}))

    assert scope.describe() == ""


def test_stakes_are_left_out_on_purpose() -> None:
    # There is no stake dimension to group by, so a claim about stakes would be
    # guesswork. The docstring says so; this stops it drifting into one.
    assert "stake" not in rb.PopulationScope().describe()
    assert not hasattr(rb.PopulationScope(), "stakes")


# --- 4. seats printed as codes ----------------------------------------------


@pytest.mark.parametrize(
    ("code", "seat"), [(-2, "BB"), (-1, "SB"), (0, "BTN"), (1, "CO"), (2, "HJ"), (6, "UTG")]
)
def test_a_seat_reads_as_a_seat(code: int, seat: str) -> None:
    assert rb.value_label("position", code) == seat
    assert rb.value_label("opponent_position", code) == seat


def test_a_value_with_no_label_renders_as_itself() -> None:
    assert rb.value_label("position", 99) == "99"
    assert rb.value_label("street", "flop") == "flop"


def test_the_picker_and_the_rows_cannot_disagree_about_a_seat() -> None:
    """Both read one table, so a code cannot be BTN in one and 0 in the other."""
    from fpdb_3_legacy.research_labels import _position_choices

    picker = {choice.label for choice in _position_choices()}

    assert {rb.value_label("position", code) for code in (-2, -1, 0, 1, 2, 6)} <= picker


def test_the_result_table_renders_its_dimensions_through_the_labels() -> None:
    tree = ast.parse((ROOT / "fpdb_3_legacy" / "GuiResearchBrowser.py").read_text())
    render = next(
        node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "_render_result"
    )

    assert "value_label" in ast.dump(render), "the rows still print raw stored values"
