"""A text filter must read back the word it was given (#411).

``_FilterRow.value()`` reads its text field through
``research_browser.text_value``, which does more than trim: an empty field is
*no filter*, ``true``/``false`` is a condition, a comma-separated field is a
list, and digits are a number. A preset is loaded into that row and read back
before it runs, so a text value has to be a word the rule keeps as it is:
``"001"`` came back as the number 1 and ``""`` as no filter at all, which ran
the preset over a different population than the one the pack declared.

The pack check (``stat_packs._research_round_trip_problem``) refuses what the
row would change. This file pins the rule against the control itself, so a
change to the row that the pack check does not follow fails here.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.qt

from fpdb_3_legacy import research_browser as rb
from fpdb_3_legacy.analytics_query import FILTERS
from fpdb_3_legacy.GuiResearchBrowser import _FilterRow
from fpdb_3_legacy.stat_packs import _research_round_trip_problem


@pytest.fixture
def row(qapp):
    return _FilterRow(rb.filter_spec("site"))


@pytest.mark.parametrize(
    ("written", "read_back"),
    [
        ("001", 1),
        ("7", 7),
        ("-5", -5),
        ("", None),
        ("   ", None),
        (" Hero ", "Hero"),
        ("true", True),
        ("False", False),
        ("Poker, Stars", ["Poker", "Stars"]),
    ],
)
def test_the_row_reads_a_text_field_into_engine_vocabulary(row, written, read_back) -> None:
    row.set_value(written)

    assert row.value() == read_back


@pytest.mark.parametrize("written", ["PokerStars", "0x10", "001.5", "1e3", "a b", "PokerStars:Hero"])
def test_a_word_the_rule_keeps_comes_back_unchanged(row, written) -> None:
    row.set_value(written)

    assert row.value() == written


@pytest.mark.parametrize(
    "written",
    ["PokerStars", "0x10", "001.5", "1e3", "a b", "001", "7", "-5", "", "   ", " Hero ", "true", "False", "Poker, Stars"],
)
def test_the_preset_check_refuses_exactly_what_the_row_changes(row, written) -> None:
    # One rule, two readers: the pack check must accept a value the row keeps
    # and refuse one it rewrites, or a preset passes validation and then runs
    # as something else.
    row.set_value(written)
    kept = row.value() == written

    assert (_research_round_trip_problem("site", written, FILTERS["site"].kind) == "") is kept


@pytest.mark.parametrize("name", ["draw_none", "blocker_none"])
def test_no_flag_at_all_survives_the_row_and_the_preset_check(qapp, name) -> None:
    # True is the engine's own "no flag at all" for these filters: the row
    # writes "True" and reads True back, so a preset may hold it.
    row = _FilterRow(rb.filter_spec(name))
    row.set_value(True)

    assert row.value() is True
    assert _research_round_trip_problem(name, True, FILTERS[name].kind) == ""
