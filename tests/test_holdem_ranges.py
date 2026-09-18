"""Filtered 13x13 range exploration (#301).

The acceptance criteria are checked in order: any analytics filter populates the
grid, the grid reconciles with the query engine's own totals, pair/suited/offsuit
classes are right, ranges can be explored without inventing the cards nobody
saw, and a cell drills down to its hands.

The corpus is the constraint that makes this testable: it stores hole cards for
one player (Boris, the hero, in all 30 hands) and for whoever reached a showdown.
75 of its 326 decisions have a known pair, over 33 hand-players, and the other
251 decisions are exactly the cards a range explorer must refuse to guess.
"""

from __future__ import annotations

import json

import pytest

from fpdb_3_legacy import analytics_profit as profit
from fpdb_3_legacy import holdem_classes as hc
from fpdb_3_legacy import holdem_ranges as ranges
from fpdb_3_legacy.analytics_query import Query, run_query
from fpdb_3_legacy.Database import Database
from fpdb_3_legacy.Importer import Importer
from tests.helpers import analytics_golden as golden

DECISIONS = 326
HANDS = 30
PAIRS = 180
KNOWN_DECISIONS = 75
UNKNOWN_DECISIONS = DECISIONS - KNOWN_DECISIONS  # 251
HERO_DECISIONS = 66
HERO_CLASSES_WITH_DATA = 19

_MODULE_STATE: list[object] = []


@pytest.fixture(scope="module")
def db(tmp_path_factory) -> Database:
    """The golden corpus imported once into a throwaway SQLite database."""
    tmp = tmp_path_factory.mktemp("ranges")
    config = golden.build_config(tmp)
    database = Database(config)
    database.recreate_tables()
    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=config, sql=None)
    importer.database = database
    for path in golden.golden_files():
        importer.addImportFile(str(path), "PokerStars")
    importer.runImport()
    _MODULE_STATE.append(importer)
    return database


def matrix_of(db, **kwargs) -> ranges.RangeMatrix:
    return ranges.build_range(db, Query(**kwargs))


# --------------------------------------------------------------------------- #
# The grid is the query.
# --------------------------------------------------------------------------- #


def test_any_filter_populates_the_grid(db):
    """The whole corpus: 169 classes, one unknown line, every decision counted."""
    matrix = matrix_of(db, metric="opportunities")
    assert len(matrix.known_cells()) == 169
    assert matrix.total_opportunities == DECISIONS
    assert matrix.total_hands == HANDS
    assert matrix.total_hand_players == PAIRS
    assert matrix.unknown_opportunities() == UNKNOWN_DECISIONS
    assert sum(cell.opportunities for cell in matrix.known_cells()) == KNOWN_DECISIONS
    assert matrix.reconcile() == ()


def test_the_grid_reconciles_with_the_query_engine(db):
    """Every cell's decisions are the engine's own count for that class."""
    matrix = matrix_of(db, metric="opportunities")
    busiest = sorted(matrix.known_cells(), key=lambda cell: -cell.opportunities)[:8]
    assert busiest[0].opportunities > 0
    for cell in busiest:
        engine = run_query(db, Query(metric="opportunities", filters={"starting_hand": cell.label}))
        assert cell.opportunities == engine.total_opportunities
    grouped = run_query(db, Query(metric="opportunities", group_by=(ranges.CLASS_DIMENSION,)))
    assert sum(row.opportunities for row in grouped.rows) == matrix.total_opportunities
    assert sum(1 for row in grouped.rows if row.group[ranges.CLASS_DIMENSION] == hc.UNKNOWN_ID) == 1


def test_the_grid_is_the_standard_13x13_of_classes(db):
    matrix = matrix_of(db, metric="opportunities")
    assert matrix.labels() == hc.grid_labels()
    assert matrix.grid()[0][0].label == "AA"
    assert matrix.grid()[12][12].label == "22"
    assert matrix.grid()[0][1].kind == "suited"
    assert matrix.grid()[1][0].kind == "offsuit"


def test_a_cell_is_addressable_by_label_and_by_id(db):
    matrix = matrix_of(db, metric="opportunities")
    assert matrix.cell("AKs").class_id == hc.class_id_of_label("AKs") == 168
    assert matrix.cell(168).label == "AKs"
    assert matrix.cell("xx").is_unknown
    with pytest.raises(hc.UnknownClass):
        matrix.cell("nope")


def test_the_cells_share_pairs_but_never_share_decisions(db):
    """Decisions partition the population; the money does not, and says so."""
    matrix = matrix_of(db, metric="opportunities")
    assert sum(cell.hand_players for cell in matrix.every_cell()) >= matrix.total_hand_players
    assert any("never sum to the total" in note for note in matrix.notes)
    paid = [cell for cell in matrix.known_cells() if cell.opportunities and cell.hand_players]
    assert paid, "the corpus has known cards in several classes"


# --------------------------------------------------------------------------- #
# The cards nobody saw.
# --------------------------------------------------------------------------- #


def test_unseen_cards_stay_in_their_own_cell(db):
    """The criterion: no invented range. 251 decisions have no pair to classify."""
    matrix = matrix_of(db, metric="opportunities")
    assert matrix.unknown_opportunities() == UNKNOWN_DECISIONS
    unknown = matrix.cell("xx")
    assert unknown.class_id == hc.UNKNOWN_ID
    assert unknown.combos == 0
    assert unknown.metric_value("sample") == UNKNOWN_DECISIONS
    assert "cards not known" in unknown.tooltip()


def test_only_known_cards_reach_the_169_classes(db):
    """Restricting to known cards moves every decision into the grid, none out."""
    known_only = matrix_of(db, metric="opportunities", filters={"hole_cards_known": True})
    assert known_only.total_opportunities == KNOWN_DECISIONS
    assert known_only.unknown_opportunities() == 0
    assert sum(cell.opportunities for cell in known_only.known_cells()) == KNOWN_DECISIONS
    assert known_only.reconcile() == ()


def test_a_player_who_never_showed_has_an_empty_grid(db):
    """Cara's cards are not in the file: the grid must be all-unknown, not empty-looking."""
    matrix = matrix_of(db, metric="opportunities", filters={"player": "Cara"})
    assert matrix.total_opportunities == 54
    assert matrix.unknown_opportunities() == 54
    assert sum(cell.opportunities for cell in matrix.known_cells()) == 0
    assert all(cell.metric_value("sample") == 0.0 for cell in matrix.known_cells())
    assert matrix.reconcile() == ()


def test_the_engine_can_also_ask_for_known_cards_directly(db):
    assert run_query(db, Query(metric="opportunities", filters={"hole_cards_known": True})).total_opportunities == KNOWN_DECISIONS
    assert run_query(db, Query(metric="opportunities", filters={"hole_cards_known": False})).total_opportunities == UNKNOWN_DECISIONS


# --------------------------------------------------------------------------- #
# A known range: the hero's.
# --------------------------------------------------------------------------- #


def test_the_hero_s_range_is_the_hero_s_hands(db):
    matrix = matrix_of(db, metric="raise_frequency", filters={"hero": True})
    assert matrix.total_opportunities == HERO_DECISIONS
    assert matrix.total_hands == HANDS
    assert matrix.unknown_opportunities() == 0, "the hero's cards are always in the file"
    with_data = [cell for cell in matrix.known_cells() if cell.opportunities]
    assert len(with_data) == HERO_CLASSES_WITH_DATA
    assert sum(cell.opportunities for cell in with_data) == HERO_DECISIONS


def test_a_cell_carries_its_counts_and_its_money(db):
    matrix = matrix_of(db, metric="raise_frequency", filters={"hero": True})
    aces = matrix.cell("AA")
    assert (aces.opportunities, aces.hands, aces.players, aces.hand_players) == (4, 2, 1, 2)
    assert aces.realized_cents == 6200
    assert aces.ev_adjusted_cents == 6200
    assert aces.combos == 6
    aks = matrix.cell("AKs")
    assert (aks.opportunities, aks.hands, aks.realized_cents) == (5, 3, 1900)


def test_the_frequency_view_is_the_query_s_own_frequency(db):
    matrix = matrix_of(db, metric="raise_frequency", filters={"hero": True})
    aces = matrix.cell("AA")
    assert aces.frequency_bp == 7500
    assert aces.actions == 3
    engine = run_query(db, Query(metric="raise_frequency", filters={"hero": True, "starting_hand": "AA"}))
    assert engine.total_actions == 3
    assert engine.rows[0].frequency_bp == aces.frequency_bp


def test_the_money_in_the_grid_is_the_report_s_money(db):
    """The grid's total is #300's unfiltered report, not the sum of overlapping cells."""
    query = Query(metric="opportunities", filters={"hero": True})
    matrix = ranges.build_range(db, query)
    report = profit.profit_report(db, profit.Query(metric="total_profit", filters={"hero": True}))
    assert matrix.total_realized_cents == report.total.realized_cents == 26500
    assert matrix.total_ev_adjusted_cents == report.total.ev_adjusted_cents
    assert sum(cell.realized_cents for cell in matrix.known_cells()) >= matrix.total_realized_cents


def test_the_four_views_read_the_same_cells(db):
    matrix = matrix_of(db, metric="raise_frequency", filters={"hero": True})
    aces = matrix.cell("AA")
    assert aces.metric_value("sample") == 4.0
    assert aces.metric_value("frequency") == 7500.0
    assert aces.metric_value("profit") == 6200.0
    assert aces.metric_value("ev_adjusted") == 6200.0
    with pytest.raises(ranges.UnknownView):
        aces.metric_value("heat")


def test_an_unknown_view_is_refused_with_the_known_ones():
    with pytest.raises(ranges.UnknownView) as caught:
        ranges.metric("heat")
    assert "heat" in str(caught.value)
    assert "frequency" in str(caught.value)


def test_the_threshold_flags_a_cell_without_hiding_its_counts(db):
    matrix = ranges.build_range(db, Query(metric="raise_frequency", filters={"hero": True}), min_sample=5)
    aces = matrix.cell("AA")
    assert not aces.sample_sufficient
    assert aces.opportunities == 4, "the flag does not change the count"
    assert matrix.sample_below_threshold() >= 1
    stricter = matrix.remarked(5)
    assert stricter.cell("AA").opportunities == aces.opportunities
    assert stricter.min_sample == 5
    assert limits_agree(stricter, matrix)


def limits_agree(left: ranges.RangeMatrix, right: ranges.RangeMatrix) -> bool:
    """Two matrices of the same population: same counts, possibly different flags."""
    return [cell.opportunities for cell in left.known_cells()] == [cell.opportunities for cell in right.known_cells()]


def test_re_marking_only_moves_the_flag(db):
    matrix = ranges.build_range(db, Query(metric="raise_frequency", filters={"hero": True}), min_sample=5)
    assert not matrix.cell("AA").sample_sufficient
    relaxed = matrix.remarked(0)
    assert relaxed.cell("AA").sample_sufficient
    assert [cell.opportunities for cell in relaxed.known_cells()] == [cell.opportunities for cell in matrix.known_cells()]
    assert matrix.min_sample == 5 and relaxed.min_sample == 0


def test_the_all_in_ev_of_a_class_is_surfaced_separately(db):
    """Hand 15's priced all-in belongs to the classes that hand's players held."""
    matrix = matrix_of(db, metric="opportunities")
    moved = [cell for cell in matrix.known_cells() if cell.ev_adjusted_pairs]
    assert moved, "the corpus prices one hand for two players"
    for cell in moved:
        assert cell.all_in_luck_cents == cell.realized_cents - cell.ev_adjusted_cents


# --------------------------------------------------------------------------- #
# Drill-down.
# --------------------------------------------------------------------------- #


def test_a_cell_narrows_to_its_own_hands(db):
    query = Query(metric="raise_frequency", filters={"hero": True})
    ids = ranges.cell_hand_ids(db, query, "AA")
    assert ids == (4, 6)
    aks = ranges.cell_hand_ids(db, query, "AKs")
    assert aks == (1, 18, 21)
    assert set(ids).isdisjoint(aks)


def test_a_cell_query_is_the_filter_the_grid_counted(db):
    query = Query(metric="opportunities", filters={"hero": True})
    narrowed = ranges.cell_query(query, "AKo")
    assert narrowed.filters == {"hero": True, "starting_hand": hc.class_id_of_label("AKo")}
    assert narrowed.limit is None
    assert run_query(db, narrowed).total_opportunities == ranges.build_range(db, query).cell("AKo").opportunities


def test_the_unknown_cell_can_be_drilled_down_too(db):
    query = Query(metric="opportunities")
    ids = ranges.cell_hand_ids(db, query, "xx")
    assert len(ids) == HANDS, "every hand has a player whose cards were not shown"
    known = ranges.cell_hand_ids(db, query, "hole_cards_known") if False else None  # noqa: F841
    assert ranges.cell_query(query, "xx").filters["starting_hand"] == hc.UNKNOWN_ID


def test_every_class_can_be_asked_for_its_hands_without_an_error(db):
    for class_id in (1, 42, 100, 168, 169, 170):
        assert isinstance(ranges.cell_hand_ids(db, Query(metric="opportunities"), class_id), tuple)


# --------------------------------------------------------------------------- #
# Scope, rendering and the JSON shape.
# --------------------------------------------------------------------------- #


def test_the_holdem_scope_is_the_population_not_the_database(db):
    assert ranges.game_categories(db, Query(metric="opportunities")) == ("holdem",)
    assert ranges.check_holdem(db, Query(metric="opportunities")) == ("holdem",)


def test_a_population_that_is_not_holdem_is_refused(db):
    """Two cards of an Omaha hand are not a Hold'em starting hand."""
    cursor = db.get_cursor()
    try:
        cursor.execute("UPDATE Gametypes SET category = 'omahahi'")
        with pytest.raises(ranges.NotHoldem) as caught:
            ranges.check_holdem(db, Query(metric="opportunities"))
        assert "omahahi" in str(caught.value)
        with pytest.raises(ranges.NotHoldem):
            ranges.build_range(db, Query(metric="opportunities"))
    finally:
        cursor.execute("UPDATE Gametypes SET category = 'holdem'")
    assert ranges.build_range(db, Query(metric="opportunities")).reconcile() == ()


def test_a_non_holdem_population_can_still_be_built_on_request(db):
    """The check is a refusal, not a restriction: a caller that knows says so."""
    cursor = db.get_cursor()
    try:
        cursor.execute("UPDATE Gametypes SET category = 'omahahi'")
        matrix = ranges.build_range(db, Query(metric="opportunities"), require_holdem=False)
        assert matrix.total_opportunities == DECISIONS
    finally:
        cursor.execute("UPDATE Gametypes SET category = 'holdem'")


def test_the_rendered_grid_names_its_view_and_its_missing_cards(db):
    rendered = matrix_of(db, metric="raise_frequency", filters={"hero": True}).render("frequency")
    lines = rendered.splitlines()
    assert "Action frequency" in lines[0]
    assert lines[1].split()[:3] == ["A", "K", "Q"]
    assert any(line.strip().startswith("xx =") for line in lines)
    assert "*" in rendered
    assert matrix_of(db, metric="opportunities").render().count("xx =") == 1


def test_an_empty_class_prints_as_absent_not_as_zero(db):
    """A class with no decision is '.' everywhere: a zero would claim an observation."""
    matrix = matrix_of(db, metric="raise_frequency", filters={"hero": True})
    empty = [cell for cell in matrix.known_cells() if not cell.opportunities]
    assert len(empty) == 169 - HERO_CLASSES_WITH_DATA
    rendered = matrix.render("frequency")
    assert rendered.count(".") >= len(empty)
    assert matrix.unknown_opportunities() == 0


def test_hiding_the_small_cells_keeps_them_out_of_the_grid(db):
    matrix = ranges.build_range(db, Query(metric="raise_frequency", filters={"hero": True}), min_sample=5)
    hidden = matrix.render("frequency", hide_small=True)
    shown = matrix.render("frequency")
    assert shown.count("*") > hidden.count("*")


def test_the_grid_serialises_whole(db):
    matrix = matrix_of(db, metric="raise_frequency", filters={"hero": True})
    payload = json.loads(json.dumps(matrix.as_dict("profit"), default=str))
    assert len(payload["grid"]) == 13
    assert len(payload["grid"][0]) == 13
    assert len(payload["cells"]) == 169
    assert payload["cells"][0]["class_id"] == hc.class_id_of_label("AA"), "cells are in grid order"
    assert payload["cells"][0]["label"] == "AA"
    assert payload["unknown"][0]["label"] == "xx"
    assert payload["total_opportunities"] == HERO_DECISIONS
    assert [view["name"] for view in payload["views"]] == ["frequency", "sample", "profit", "ev_adjusted"]
    assert payload["values"][0][0] == matrix.cell("AA").metric_value("profit")


def test_a_selection_of_classes_covers_its_combinations(db):
    assert ranges.share_of_range(["AA", "AKs", "AKo"]) == pytest.approx(22 / 1326)
    assert ranges.share_of_range([]) == 0.0
