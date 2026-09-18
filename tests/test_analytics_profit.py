"""Action profitability and EV reporting (#300).

The acceptance criteria are checked in order: profit for arbitrary filters, a
split by action and by sizing bucket, all-in EV kept apart from realized profit,
labels that do not pretend to be solver EV, hands that can be opened for review,
and totals reconciled with the money already in the database.

Every number comes from the golden corpus, which is fixed: 31 hands, 341
decisions, 6 players dealt into all 31 hands, 186 distinct (hand, player) pairs,
one game type at $2/$4-class stakes with a 200-cent big blind, and rake-free --
so the money of the whole corpus has to add up to exactly zero. The corpus
prices the all-in equity of exactly one hand (15), for two of its players, which
is what makes the EV surface testable rather than decorative.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fpdb_3_legacy import analytics_profit as profit
from fpdb_3_legacy.analytics_query import Query, run_query
from fpdb_3_legacy.Database import Database
from fpdb_3_legacy.Importer import Importer
from tests.helpers import analytics_golden as golden

# Read off the corpus (see the module docstring).
DECISIONS = 341
HANDS = 31
PLAYERS = 6
PAIRS = 186
HERO_DECISIONS = 69
HERO_REALIZED = 27400
OPPONENT_REALIZED = -27400
EV_ADJUSTED = -40
PRICED_PAIRS = 2
BIG_BLIND_CENTS = 200

# The hand whose all-in equity fpdb could price, and the naive sum a
# per-decision attribution would report -- the number this module refuses.
PRICED_HAND = 15
NAIVE_DECISION_SUM = -29800

_MODULE_STATE: list[object] = []


@pytest.fixture(scope="module")
def db(tmp_path_factory) -> Database:
    """The golden corpus imported once into a throwaway SQLite database."""
    tmp = tmp_path_factory.mktemp("profit")
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


def report(db, *, rake: str = "contributed", min_sample: int = 0, **query_kwargs) -> profit.ProfitReport:
    """A report of a query built from the keyword arguments, with the reporting knobs."""
    return profit.profit_report(db, Query(**query_kwargs), rake=rake, min_sample=min_sample)


# --------------------------------------------------------------------------- #
# The meanings of "profit", and the one that is refused.
# --------------------------------------------------------------------------- #


def test_the_catalog_names_the_four_meanings_of_profit():
    names = [spec.name for spec in profit.semantics_catalog()]
    assert names == ["realized", "ev_adjusted", "all_in_luck", "immediate_action_ev"]
    assert profit.REPORTED_SEMANTICS == ("realized", "ev_adjusted", "all_in_luck")


def test_only_the_theoretical_figure_is_marked_not_computable():
    computable = {spec.name for spec in profit.semantics_catalog() if spec.computable}
    assert computable == {"realized", "ev_adjusted", "all_in_luck"}
    assert profit.semantics("immediate_action_ev").kind == "not_computable"


def test_the_conditional_result_is_labelled_as_a_hand_result_not_an_ev():
    """The criterion is about wording, so the wording is what is asserted."""
    realized = profit.semantics("realized")
    assert realized.kind == "hand_result"
    assert "hand" in realized.definition.lower()
    assert "not the expected value" in realized.caveat


def test_the_refusal_says_why_it_cannot_be_computed():
    with pytest.raises(profit.NotComputable) as caught:
        profit.immediate_action_ev(Query(metric="total_profit"))
    message = str(caught.value)
    assert "not computable" in message
    assert "range" in message, "the reason is the missing counterfactual, not a missing column"


def test_an_unknown_semantics_name_is_refused_with_the_known_ones():
    with pytest.raises(KeyError) as caught:
        profit.semantics("solver_ev")
    assert "solver_ev" in str(caught.value)
    assert "all_in_luck" in str(caught.value)


def test_each_meaning_carries_a_distinct_label_and_its_own_caveat():
    specs = profit.semantics_catalog()
    assert len({spec.label for spec in specs}) == len(specs)
    assert all(spec.caveat for spec in specs)


# --------------------------------------------------------------------------- #
# The whole corpus: the money, its sample, and the unit it is in.
# --------------------------------------------------------------------------- #


def test_the_whole_corpus_reports_its_sample_and_its_money(db):
    total = report(db, metric="total_profit").total
    assert (total.opportunities, total.hands, total.players, total.hand_players) == (
        DECISIONS,
        HANDS,
        PLAYERS,
        PAIRS,
    )


def test_the_corpus_is_zero_sum_once_per_hand_player(db):
    """Rake-free and closed: the report must find exactly the money that is there."""
    total = report(db, metric="total_profit").total
    assert total.realized_cents == 0
    assert total.rake == {"dealt": 0, "contributed": 0, "weighted": 0}


def test_a_decision_level_sum_is_not_the_report(db):
    """The rule the report is built on, contradicted by the naive alternative."""
    cursor = db.get_cursor()
    cursor.execute(
        "SELECT SUM(HP.totalProfit) FROM HandsActions A"
        " JOIN HandsPlayers HP ON HP.handId = A.handId AND HP.playerId = A.playerId",
    )
    naive = int(cursor.fetchone()[0])
    assert naive == NAIVE_DECISION_SUM
    assert naive != report(db, metric="total_profit").total.realized_cents


def test_the_all_in_ev_is_surfaced_apart_from_realized_profit(db):
    total = report(db, metric="total_profit").total
    assert total.ev_adjusted_cents == EV_ADJUSTED
    assert total.all_in_luck_cents == total.realized_cents - total.ev_adjusted_cents == 40


def test_the_all_in_adjustment_names_the_pairs_it_came_from(db):
    total = report(db, metric="total_profit").total
    assert total.ev_adjusted_pairs == PRICED_PAIRS
    assert total.ev_adjusted_pairs <= total.hand_players


def test_a_non_all_in_population_has_no_adjustment_at_all(db):
    """'EV-adjusted' must not move a hand that never faced a priced all-in."""
    total = report(db, metric="total_profit", filters={"hero": True}).total
    assert (total.ev_adjusted_cents, total.all_in_luck_cents, total.ev_adjusted_pairs) == (
        HERO_REALIZED,
        0,
        0,
    )


def test_the_priced_hand_is_the_hand_the_adjustment_lives_in(db):
    """Six players are dealt into the hand, but only two of them were priced."""
    total = report(db, metric="total_profit", filters={"hand_id": [PRICED_HAND]}).total
    assert (total.hand_players, total.ev_adjusted_pairs) == (PLAYERS, 2)
    assert total.realized_cents == 0, "the hand is zero-sum, rake-free, like every other"
    assert total.ev_adjusted_cents == EV_ADJUSTED
    assert total.all_in_luck_cents == 40


def test_the_all_in_decisions_of_the_corpus_are_three_over_two_hands(db):
    report_ = report(db, metric="total_profit", filters={"all_in": True})
    assert report_.total.opportunities == 3
    assert report_.total.hands == 2
    assert report_.total.ev_adjusted_pairs == PRICED_PAIRS


# --------------------------------------------------------------------------- #
# Reconciliation: the report and the rows it was built from.
# --------------------------------------------------------------------------- #


def test_the_unfiltered_report_equals_the_stored_money(db):
    cursor = db.get_cursor()
    cursor.execute("SELECT SUM(totalProfit), COUNT(*) FROM HandsPlayers")
    stored, pairs = cursor.fetchone()
    total = report(db, metric="total_profit").total
    assert int(stored) == total.realized_cents
    assert int(pairs) == total.hand_players == PAIRS


def test_a_player_dimension_partitions_the_money(db):
    """A seat is a property of the hand-player, so its groups do not overlap."""
    report_ = report(db, metric="total_profit", group_by=("player",))
    assert not report_.overlapping_groups
    assert len(report_.rows) == PLAYERS
    assert sum(row.realized_cents for row in report_.rows) == report_.total.realized_cents == 0
    assert sum(row.hand_players for row in report_.rows) == PAIRS


def test_the_per_player_money_is_the_pair_level_money(db):
    report_ = report(db, metric="total_profit", group_by=("player",))
    assert {row.group["player"]: row.realized_cents for row in report_.rows} == {
        "Anna": 20000,
        "Boris": HERO_REALIZED,
        "Cara": -11400,
        "Dave": -3100,
        "Erin": -6200,
        "Frank": -26700,
    }


def test_the_hero_and_the_opponents_add_up_to_the_corpus(db):
    hero = report(db, metric="total_profit", filters={"hero": True}).total
    opponents = report(db, metric="total_profit", filters={"hero": False}).total
    assert (hero.opportunities, opponents.opportunities) == (HERO_DECISIONS, DECISIONS - HERO_DECISIONS)
    assert (hero.realized_cents, opponents.realized_cents) == (HERO_REALIZED, OPPONENT_REALIZED)
    assert hero.realized_cents + opponents.realized_cents == 0
    assert hero.hand_players + opponents.hand_players == PAIRS


def test_a_position_dimension_also_partitions_the_money(db):
    """Position is per hand-player too: six groups, one pair in each."""
    report_ = report(db, metric="total_profit", group_by=("position",))
    assert not report_.overlapping_groups
    assert sum(row.hand_players for row in report_.rows) == PAIRS
    assert sum(row.realized_cents for row in report_.rows) == 0


# --------------------------------------------------------------------------- #
# The examples the issue asks for.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("filters", "opportunities", "hands", "realized"),
    [
        ({"pot_type": "three_bet"}, 23, 4, -5600),
        ({"primary_situation": "facing_3bet"}, 12, 3, -22500),
        ({"primary_situation": "facing_3bet", "response": "call"}, 2, 2, -21600),
        ({"primary_situation": "three_bet", "response": "raise"}, 3, 3, 26500),
        ({"primary_situation": "cbet", "sizing_bucket": ["25-33", "33-40"]}, 2, 2, 1600),
        ({"primary_situation": "cbet_spot", "response": "check"}, 8, 7, -2700),
        ({"primary_situation": "open_raise", "position": "co"}, 20, 20, 17400),
        ({"situation": "squeeze"}, 1, 1, 1300),
    ],
)
def test_the_profitable_populations_the_issue_names(db, filters, opportunities, hands, realized):
    total = report(db, metric="total_profit", filters=filters).total
    assert (total.opportunities, total.hands) == (opportunities, hands)
    assert total.realized_cents == realized


def test_a_spot_the_corpus_never_plays_reports_zeros_not_an_error(db):
    """'Raising a turn probe' is not in the corpus; the report must say so quietly."""
    report_ = report(db, metric="total_profit", filters={"primary_situation": "probe", "response": "raise"})
    assert report_.total.opportunities == 0
    assert report_.total.realized_cents == 0
    assert report_.total.bb_per_100 is None
    assert report_.hand_ids == ()


def test_profit_per_hand_and_per_opportunity_use_their_own_denominators(db):
    total = report(db, metric="total_profit", filters={"hero": True}).total
    assert total.realized_per_hand_cents == pytest.approx(HERO_REALIZED / HANDS)
    assert total.realized_per_opportunity_cents == pytest.approx(HERO_REALIZED / HERO_DECISIONS)
    assert total.realized_per_hand_cents != total.realized_per_opportunity_cents


def test_a_filter_selecting_one_player_still_reports_their_hands(db):
    report_ = report(db, metric="total_profit", filters={"player": "Boris"})
    assert report_.total.realized_cents == HERO_REALIZED
    assert len(report_.hand_ids) == HANDS


# --------------------------------------------------------------------------- #
# Splitting by action and by sizing bucket.
# --------------------------------------------------------------------------- #


def test_a_sizing_split_overlaps_and_says_so(db):
    """The headline semantic: a decision split is not a split of the money."""
    report_ = report(db, metric="total_profit", filters={"primary_situation": "cbet"}, group_by=("sizing_bucket",))
    assert report_.overlapping_groups
    assert sum(row.hand_players for row in report_.rows) > report_.total.hand_players
    assert sum(row.realized_cents for row in report_.rows) > report_.total.realized_cents
    assert any("groups overlap" in note for note in report_.notes)


def test_the_sizing_rows_the_report_shows(db):
    report_ = report(db, metric="total_profit", filters={"primary_situation": "cbet"}, group_by=("sizing_bucket",))
    by_bucket = {row.group["sizing_bucket"]: row for row in report_.rows}
    assert by_bucket["50-66"].opportunities == 12
    assert by_bucket["50-66"].realized_cents == 7800
    assert by_bucket["66-80"].realized_cents == 5600
    assert by_bucket["0-25"].realized_cents == 800


def test_the_bucket_filter_selects_exactly_what_the_bucket_groups(db):
    """The histogram and the drill-down must read the same boundaries."""
    labels = [row.group["sizing_bucket"] for row in report(db, metric="opportunities", group_by=("sizing_bucket",)).rows]
    for label in ("0-25", "25-33", "50-66", "150+"):
        assert label in labels
        by_dimension = run_query(
            db,
            Query(metric="opportunities", group_by=("sizing_bucket",)),
        )
        counted = next(row.opportunities for row in by_dimension.rows if row.group["sizing_bucket"] == label)
        filtered = run_query(db, Query(metric="opportunities", filters={"sizing_bucket": label}))
        assert counted == filtered.total_opportunities


def test_an_action_split_overlaps_too(db):
    report_ = report(db, metric="total_profit", filters={"role": "aggressor"}, group_by=("street",))
    by_street = {row.group["street"]: row for row in report_.rows}
    assert by_street["preflop"].opportunities == 36
    assert by_street["flop"].realized_cents == -3400
    assert sum(row.hand_players for row in report_.rows) >= report_.total.hand_players


def test_a_board_texture_split_is_available_per_street(db):
    report_ = report(db, metric="total_profit", filters={"primary_situation": "cbet_spot"}, group_by=("board_rank",))
    by_rank = {row.group["board_rank"]: row.realized_cents for row in report_.rows}
    assert by_rank == {"broadway": -2400, "king-high": -1800, "middle": 1500}


def test_a_row_can_be_fetched_by_its_group_values(db):
    report_ = report(db, metric="total_profit", group_by=("player", "position"))
    row = report_.row(player="Boris", position=1)
    assert row.realized_cents == HERO_REALIZED
    with pytest.raises(KeyError):
        report_.row(player="Boris")
    with pytest.raises(KeyError):
        report_.row(player="Nobody", position=1)


# --------------------------------------------------------------------------- #
# Big blinds: the unit, and the populations that have none.
# --------------------------------------------------------------------------- #


def test_bb_per_100_is_the_per_hand_bb_result_per_hundred_hands(db):
    total = report(db, metric="total_profit", filters={"hero": True}).total
    assert total.bb_pairs == HANDS
    assert total.bb_profit == pytest.approx(HERO_REALIZED / BIG_BLIND_CENTS)
    assert total.bb_per_100 == pytest.approx(100 * total.bb_profit / HANDS)


def test_the_ev_adjusted_figure_has_a_bb_form_too(db):
    total = report(db, metric="total_profit").total
    assert total.ev_bb_per_100 == pytest.approx(round(100 * (EV_ADJUSTED / BIG_BLIND_CENTS) / PAIRS, 4))
    assert total.ev_bb_per_100 != total.bb_per_100


def test_a_population_without_a_usable_big_blind_refuses_to_guess(db):
    """Fixed-limit rows store -1 in the game type: dividing by it would be a lie."""
    cursor = db.get_cursor()
    try:
        cursor.execute("UPDATE Gametypes SET bigBlind = -1")
        total = report(db, metric="total_profit").total
        assert total.bb_pairs == 0
        assert total.bb_per_100 is None
        assert total.ev_bb_per_100 is None
        assert any("no usable big" in note for note in report(db, metric="total_profit").notes)
    finally:
        cursor.execute("UPDATE Gametypes SET bigBlind = 200")
    assert report(db, metric="total_profit").total.bb_per_100 == 0.0


# --------------------------------------------------------------------------- #
# Rake: three attributions, one chosen, and the note that says which.
# --------------------------------------------------------------------------- #


@pytest.fixture
def raked(db):
    """A hand rake written onto the corpus, removed again afterwards.

    The corpus is rake-free by construction, so the attributions are exercised
    here against money that is actually in the columns; the derivation itself
    belongs to the derived stats, not to this report.
    """
    cursor = db.get_cursor()
    cursor.execute("UPDATE HandsPlayers SET rakeDealt = 100, rakeContributed = 200, rakeWeighted = 300")
    try:
        yield
    finally:
        cursor.execute("UPDATE HandsPlayers SET rakeDealt = 0, rakeContributed = 0, rakeWeighted = 0")


def test_no_rake_is_reported_as_no_rake(db):
    report_ = report(db, metric="total_profit")
    assert report_.total.rake_cents == 0
    assert any("no rake is stored" in note for note in report_.notes)


def test_the_three_attributions_are_reportable_separately(db, raked):
    report_ = report(db, metric="total_profit")
    assert report_.total.rake == {"dealt": 100 * PAIRS, "contributed": 200 * PAIRS, "weighted": 300 * PAIRS}


def test_fractional_rake_allocations_are_not_rounded_to_zero(db, raked):
    cursor = db.get_cursor()
    cursor.execute(
        "UPDATE HandsPlayers SET rakeContributed = 1.0 / 6 "
        "WHERE handId = 1 AND playerId = (SELECT id FROM Players WHERE name = 'Anna')",
    )
    try:
        total = report(db, metric="total_profit").total
        expected = 200 * (PAIRS - 1) + (1 / 6)
        assert total.rake_cents == pytest.approx(expected)
        assert total.rake_cents > 0
    finally:
        cursor.execute("UPDATE HandsPlayers SET rakeContributed = 200")


def test_the_chosen_attribution_is_the_one_in_the_money_column(db, raked):
    for attribution, expected in (("dealt", 100), ("contributed", 200), ("weighted", 300)):
        report_ = report(db, metric="total_profit", rake=attribution)
        assert report_.total.rake_cents == expected * PAIRS
        assert any(f"attributed by {attribution}" in note for note in report_.notes)


def test_rake_is_reported_per_hand_as_well_as_in_total(db, raked):
    total = report(db, metric="total_profit").total
    assert total.rake_per_hand_cents == pytest.approx(200 * PAIRS / HANDS)


def test_an_unknown_attribution_is_refused_with_the_known_ones(db):
    with pytest.raises(ValueError) as caught:
        profit.profit_report(db, Query(metric="total_profit"), rake="split")
    assert "split" in str(caught.value)
    assert "contributed" in str(caught.value)


def test_rake_is_a_property_of_the_hand_not_of_the_action(db, raked):
    """A split by action pays the same rake twice; the report says whose it is."""
    report_ = report(db, metric="total_profit", group_by=("player",))
    assert sum(row.rake_cents for row in report_.rows) == report_.total.rake_cents


# --------------------------------------------------------------------------- #
# Sample sizes and the rendering.
# --------------------------------------------------------------------------- #


def test_a_row_below_the_threshold_is_flagged_not_hidden(db):
    report_ = report(db, metric="total_profit", group_by=("sizing_bucket",), min_sample=10)
    small = [row for row in report_.rows if not row.sample_sufficient]
    assert small, "the corpus has buckets with a handful of decisions"
    assert all(row.opportunities < 10 for row in small)
    assert any("fewer than 10 decisions" in note for note in report_.notes)


def test_the_total_is_flagged_by_the_same_threshold(db):
    report_ = report(db, metric="total_profit", min_sample=DECISIONS + 1)
    assert not report_.total.sample_sufficient


def test_hiding_the_small_rows_leaves_the_total_alone(db):
    report_ = report(db, metric="total_profit", group_by=("sizing_bucket",), min_sample=10)
    rendered = report_.render(hide_small=True)
    assert rendered.count("50-66") == 1
    assert "0-25" not in rendered
    assert str(report_.total.realized_cents) in rendered


def test_an_ungrouped_report_prints_its_one_row_once(db):
    rendered = report(db, metric="total_profit").render()
    assert rendered.count("\n") == sum(1 for _ in rendered.splitlines()) - 1
    data_lines = [line for line in rendered.splitlines() if line.strip().startswith(("341", "69"))]
    assert len(data_lines) == 1


def test_the_rendered_report_names_the_unit_the_rake_and_the_notes(db):
    rendered = report(db, metric="total_profit", rake="weighted").render()
    assert "money in cents" in rendered
    assert "weighted rake" in rendered
    assert "note:" in rendered


def test_a_report_that_hides_nothing_does_not_say_it_hid_anything(db):
    rendered = report(db, metric="total_profit", group_by=("player",)).render()
    assert "not shown" not in rendered
    shown = [line for line in rendered.splitlines() if line.strip().startswith(("Anna", "Boris", "Cara", "Dave", "Erin", "Frank"))]
    assert len(shown) == PLAYERS


def test_limiting_the_rows_does_not_limit_the_population(db):
    report_ = report(db, metric="total_profit", group_by=("player",), limit=2)
    assert report_.total.opportunities == DECISIONS
    assert any("paging is ignored" in note for note in report_.notes)
    rendered = report_.render(limit=2)
    assert "4 row(s) not shown" in rendered


# --------------------------------------------------------------------------- #
# Drill-down: the hands behind a row.
# --------------------------------------------------------------------------- #


def test_the_report_carries_the_matching_hand_ids_sorted_and_distinct(db):
    report_ = report(db, metric="total_profit", filters={"pot_type": "three_bet"})
    assert report_.hand_ids == (4, 5, 6, 15)


def test_hand_ids_can_be_switched_off_or_capped(db):
    quiet = profit.profit_report(db, Query(metric="total_profit"), with_hand_ids=False)
    assert quiet.hand_ids == ()
    capped = profit.profit_report(db, Query(metric="total_profit"), hand_id_limit=3)
    assert len(capped.hand_ids) == 3


def test_narrowing_a_row_reproduces_its_own_hands(db):
    grouped = Query(metric="total_profit", filters={"primary_situation": "cbet"}, group_by=("sizing_bucket",))
    row = profit.profit_report(db, grouped).row(sizing_bucket="50-66")
    narrowed = profit.narrow_query(Query(metric="total_profit", filters={"primary_situation": "cbet"}), {"sizing_bucket": "50-66"})
    ids = profit.matching_hand_ids(db, narrowed)
    assert len(ids) == row.hands == 11
    assert ids == (7, 11, 12, 13, 14, 16, 17, 18, 19, 20, 25)


def test_narrowing_keeps_the_filters_the_report_was_given(db):
    query = Query(metric="total_profit", filters={"hero": True})
    narrowed = profit.narrow_query(query, {"street": "flop"})
    assert narrowed.filters == {"hero": True, "street": "flop"}
    assert narrowed.limit == query.limit


def test_narrowing_normalizes_ranges_nulls_and_tournament_ids():
    base = Query(metric="total_profit", filters={"hero": True})
    assert profit.narrow_query(base, {"effective_stack_bb": 20}).filters == {
        "hero": True,
        "effective_stack_bb": [20, 20],
    }
    assert profit.narrow_query(base, {"board_rank": None}).filters == {
        "hero": True,
        "board_rank": {"is_null": True},
    }
    assert profit.narrow_query(base, {"tournament": 1234}).filters == {
        "hero": True,
        "tournament_id": 1234,
    }


def test_limit_dimension_uses_a_safe_sql_alias(db):
    report_ = report(db, metric="total_profit", group_by=("limit",))
    assert report_.rows
    assert {row.group["limit"] for row in report_.rows} == {"nl"}
    assert "AS limit_" in report_.compiled[0].sql


def test_narrowing_by_a_dimension_without_a_filter_is_refused_by_name(db):
    with pytest.raises(ValueError) as caught:
        profit.narrow_query(Query(metric="total_profit"), {"no_such_dimension": 1})
    assert "no_such_dimension" in str(caught.value)


def test_a_group_can_be_asked_for_its_hands_directly(db):
    query = Query(metric="total_profit", filters={"role": "aggressor"})
    flop = profit.matching_hand_ids(db, profit.narrow_query(query, {"street": "flop"}))
    preflop = profit.matching_hand_ids(db, profit.narrow_query(query, {"street": "preflop"}))
    assert len(flop) == 24
    assert len(preflop) == 30
    # The added limped-pot hand has a flop aggressor but no matching preflop
    # aggressor; all earlier corpus flop matches remain in the preflop set.
    assert set(flop) - {31} < set(preflop)


# --------------------------------------------------------------------------- #
# The compiled statements and the JSON shape, for the browser (#303).
# --------------------------------------------------------------------------- #


def test_the_money_query_is_compiled_without_running_it(db):
    compiled = profit.compile_profit_query(
        Query(metric="total_profit", filters={"player": "Boris"}),
        placeholder="?",
        backend="sqlite",
    )
    assert "SELECT DISTINCT" in compiled.sql
    assert "JOIN HandsPlayers HP ON HP.handId = P.handId AND HP.playerId = P.playerId" in compiled.sql
    assert "SUM(HP.totalProfit) AS realized_cents" in compiled.sql
    assert compiled.params == ("Boris",)
    assert compiled.group_by == ()


def test_an_unknown_dimension_is_refused_before_any_sql_is_built():
    with pytest.raises(ValueError) as caught:
        profit.compile_profit_query(Query(metric="total_profit", group_by=("no_such_dimension",)))
    assert "no_such_dimension" in str(caught.value)


def test_the_report_runs_both_statements_and_keeps_them(db):
    report_ = report(db, metric="total_profit", filters={"hero": True}, group_by=("position",))
    money, counts = report_.compiled
    assert money.sql != counts.sql
    assert "P.position" in money.sql
    assert money.group_by == ("position",)
    assert counts.group_by == ("position",)


def test_a_grouped_report_total_comes_from_an_ungrouped_statement(db):
    report_ = report(db, metric="total_profit", group_by=("sizing_bucket",))
    assert "GROUP BY" in report_.compiled[0].sql
    assert report_.total.hand_players == PAIRS, "the total is the population, not the sum of the rows"


def test_the_report_serialises_whole_and_readably(db):
    report_ = report(db, metric="total_profit", filters={"hero": True})
    payload = json.dumps(report_.as_dict(), default=str)
    decoded = json.loads(payload)
    assert decoded["total"]["realized_cents"] == HERO_REALIZED
    assert decoded["total"]["hand_players"] == HANDS
    assert [spec["name"] for spec in decoded["semantics"]] == [
        "realized",
        "ev_adjusted",
        "all_in_luck",
        "immediate_action_ev",
    ]
    assert decoded["rows"][0]["bb_per_100"] == pytest.approx(441.9355)


def test_a_drill_down_query_fits_in_the_browser_shape(db):
    """What #303 will call: a query, its rows, the hands and the semantics."""
    report_ = report(db, metric="total_profit", filters={"role": "aggressor"}, group_by=("street",))
    payload = report_.as_dict()
    for key in ("metric", "filters", "group_by", "rows", "total", "hand_ids", "notes", "semantics", "sql"):
        assert key in payload
    assert payload["rows"] and all(row["opportunities"] <= DECISIONS for row in payload["rows"])
    assert len(payload["hand_ids"]) == HANDS
    assert Path("fpdb_3_legacy/analytics_profit.py").exists()
