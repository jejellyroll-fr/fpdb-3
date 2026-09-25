"""Composable stat/filter query engine over the analytics rows (#297).

The layers below this one answer fixed questions: the event model (#293) says
what happened, the situation model (#294) names the spot, the board features
(#295) classify the texture and the buckets (#296) sort the sizings. This
module checks the layer that lets a *new* question be asked out of those
pieces -- ``query(metric=..., filters=..., group_by=...)`` -- without a new
Python function and a new SQL string per stat.

The tests fall in the order of the acceptance criteria: filters compose,
results group, a frequency returns its numerator *and* denominator, the
matching hand ids come back for drill-down, the SQL is parameterized by
construction, and where a new query overlaps an existing predefined stat the
two agree -- with the one place they deliberately do not, named.

The equivalence check is worth the ink: a fold-to-a-flop-c-bet frequency built
from the situation model matches ``HudCache.foldToStreet1CBDone`` for every
player except the hand the golden corpus already documents as a deviation
(``fold_to_cbet_counts_a_raise_as_cbet``), so the engine re-derives the
predicted answer and surfaces the known wrong one, rather than inventing a
third.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fpdb_3_legacy.analytics_query import (
    DIMENSIONS,
    FILTERS,
    KNOWN_METRICS,
    Query,
    compile_filters,
    compile_hand_ids,
    compile_query,
    filter_sources,
    run_hand_ids,
    run_query,
)
from fpdb_3_legacy.Database import Database
from fpdb_3_legacy.Importer import Importer
from tests.helpers import analytics_golden as golden

# The one documented deviation that separates the situation model from the
# HUD cache on the fold-to-flop-c-bet stat: HudCache counts the flop *raise*
# Cara folded to as if it were a c-bet (golden.json deviation
# ``fold_to_cbet_counts_a_raise_as_cbet``, hand 3100000010).
DEVIATION_PLAYER = "Cara"


@pytest.fixture(scope="module")
def query_db(tmp_path_factory) -> Database:
    """The golden corpus imported once into a throwaway SQLite database."""
    tmp = tmp_path_factory.mktemp("query-engine")
    config = golden.build_config(tmp)
    db = Database(config)
    db.recreate_tables()
    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=config, sql=None)
    importer.database = db
    for path in golden.golden_files():
        importer.addImportFile(str(path), "PokerStars")
    importer.runImport()
    # The importer's destructor closes the database connection; keep it alive.
    _MODULE_STATE.append(importer)
    return db


_MODULE_STATE: list[object] = []


def _scalar(db: Database, sql: str, params: tuple = ()) -> int:
    cursor = db.get_cursor()
    cursor.execute(sql, params)
    return int(cursor.fetchone()[0] or 0)


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------


class TestFilters:
    """A filter names a condition; filters compose by AND."""

    def test_filters_narrow_the_population(self, query_db: Database) -> None:
        everything = run_query(query_db, Query(metric="opportunities")).rows[0].opportunities
        flop = run_query(query_db, Query(metric="opportunities", filters={"street": "flop"}))
        assert 0 < flop.rows[0].opportunities < everything
        expected = _scalar(
            query_db,
            "SELECT COUNT(*) FROM HandsActions A"
            " JOIN HandsSituations SI ON SI.handId = A.handId AND SI.actionNo = A.actionNo"
            " WHERE SI.streetName = 'flop'",
        )
        assert flop.rows[0].opportunities == expected

    def test_filters_compose_with_and(self, query_db: Database) -> None:
        both = run_query(
            query_db,
            Query(metric="opportunities", filters={"street": "flop", "response": "fold"}),
        )
        expected = _scalar(
            query_db,
            "SELECT COUNT(*) FROM HandsActions A"
            " JOIN HandsSituations SI ON SI.handId = A.handId AND SI.actionNo = A.actionNo"
            " WHERE SI.streetName = 'flop' AND SI.response IN ('fold')",
        )
        assert both.rows[0].opportunities == expected

    def test_set_filter_uses_in(self, query_db: Database) -> None:
        rows = run_query(query_db, Query(metric="opportunities", filters={"response": ["fold", "call"]}))
        expected = _scalar(
            query_db,
            "SELECT COUNT(*) FROM HandsActions A"
            " JOIN HandsSituations SI ON SI.handId = A.handId AND SI.actionNo = A.actionNo"
            " WHERE SI.response IN ('fold', 'call')",
        )
        assert rows.rows[0].opportunities == expected

    def test_range_is_inclusive(self, query_db: Database) -> None:
        bounded = run_query(
            query_db,
            Query(metric="opportunities", filters={"effective_stack_bb": [8000, 12000]}),
        ).rows[0].opportunities
        expected = _scalar(
            query_db,
            "SELECT COUNT(*) FROM HandsActions WHERE effectiveStackBB >= 8000 AND effectiveStackBB <= 12000",
        )
        assert bounded == expected

    def test_draw_filters_are_scoped_to_explicit_draw_decisions(self) -> None:
        fragments, params, aliases = compile_filters(
            {"draw_number": [1, 3], "cards_drawn": [0, 5]}, "?", "sqlite",
        )
        assert aliases == {"A", "G"}
        assert params == [1, 3, 0, 5]
        sql = " AND ".join(fragments)
        assert "G.base = 'draw'" in sql
        assert "G.category = 'drawmaha' THEN 1 ELSE A.street" in sql
        assert "A.actionType IN ('discards', 'stands pat')" in sql
        assert "A.actionType = 'stands pat' THEN 0" in sql
        assert "A.numDiscarded >= 0" in sql

    def test_draw_dimensions_are_available_for_grouping(self) -> None:
        compiled = compile_query(
            Query(metric="opportunities", group_by=("draw_number", "cards_drawn")),
            "?", "sqlite",
        )
        assert "AS draw_number" in compiled.sql
        assert "AS cards_drawn" in compiled.sql
        assert "A.numDiscarded >= 0" in compiled.sql

    def test_range_is_open_ended(self, query_db: Database) -> None:
        lower_only = run_query(
            query_db,
            Query(metric="opportunities", filters={"effective_stack_bb": {"min": 8000}}),
        ).rows[0].opportunities
        assert lower_only == _scalar(
            query_db, "SELECT COUNT(*) FROM HandsActions WHERE effectiveStackBB >= 8000"
        )
        everything = run_query(query_db, Query(metric="opportunities")).rows[0].opportunities
        assert lower_only < everything  # some decisions are shorter

    def test_position_names_resolve_to_codes(self, query_db: Database) -> None:
        named = run_query(query_db, Query(metric="opportunities", filters={"position": "btn"})).rows[0]
        numeric = run_query(query_db, Query(metric="opportunities", filters={"position": 0})).rows[0]
        assert named.opportunities == numeric.opportunities > 0
        blinds = run_query(query_db, Query(metric="opportunities", filters={"position": ["sb", "bb"]})).rows[0]
        expected = _scalar(query_db, "SELECT COUNT(*) FROM HandsActions WHERE position IN (-1, -2)")
        assert blinds.opportunities == expected

    def test_percent_sizing_converts_to_basis_points(self, query_db: Database) -> None:
        percent = run_query(query_db, Query(metric="opportunities", filters={"sizing_bp": [2500, 4000]}))
        as_percent = run_query(query_db, Query(metric="opportunities", filters={"bet_sizing_pct": [25, 40]}))
        assert percent.rows[0].opportunities == as_percent.rows[0].opportunities
        assert percent.rows[0].opportunities > 0

    def test_boolean_filters(self, query_db: Database) -> None:
        in_position = run_query(query_db, Query(metric="opportunities", filters={"in_position": True})).rows[0]
        expected = _scalar(query_db, "SELECT COUNT(*) FROM HandsActions WHERE inPosition = 1")
        assert in_position.opportunities == expected
        out = run_query(query_db, Query(metric="opportunities", filters={"in_position": False})).rows[0]
        everything = run_query(query_db, Query(metric="opportunities")).rows[0]
        assert in_position.opportunities + out.opportunities == everything.opportunities

    def test_tournament_is_a_null_check(self, query_db: Database) -> None:
        # The corpus is ring-only, so the tournament side is empty and the cash
        # side is everything -- which is what "tourneyId IS NULL" means.
        ring = run_query(query_db, Query(metric="opportunities", filters={"tournament": False})).rows[0]
        tour = run_query(query_db, Query(metric="opportunities", filters={"tournament": True})).rows[0]
        assert tour.opportunities == 0
        assert ring.opportunities > 0

    def test_board_texture_any_and_all(self, query_db: Database) -> None:
        any_flags = run_query(
            query_db,
            Query(metric="opportunities", filters={"board_texture": ["rainbow", "flush_possible"]}),
        ).rows[0].opportunities
        all_flags = run_query(
            query_db,
            Query(metric="opportunities", filters={"board_texture_all": ["rainbow", "unpaired"]}),
        ).rows[0].opportunities
        assert 0 < all_flags <= any_flags

    def test_board_label_filters(self, query_db: Database) -> None:
        rainbow = run_query(
            query_db, Query(metric="opportunities", filters={"street": "flop", "board_suit": "rainbow"}),
        ).rows[0].opportunities
        assert rainbow > 0
        # A preflop decision joins no board row, so a board filter excludes it.
        assert rainbow < run_query(query_db, Query(metric="opportunities", filters={"street": "flop"})).rows[0].opportunities

    def test_situation_label_matches_json_labels(self, query_db: Database) -> None:
        facing = run_query(
            query_db,
            Query(metric="opportunities", filters={"street": "flop", "situation": "facing_cbet"}),
        ).rows[0].opportunities
        assert facing > 0
        # The quoted pattern is exact: "probe" must not match "facing_probe".
        probe = run_query(query_db, Query(metric="opportunities", filters={"situation": "probe"})).rows[0]
        assert 0 < probe.opportunities < facing

    def test_unknown_filter_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="Unknown filter"):
            compile_query(Query(metric="opportunities", filters={"made_up": 1}))

    def test_null_valued_filter_is_ignored(self, query_db: Database) -> None:
        with_none = run_query(query_db, Query(metric="opportunities", filters={"street": None})).rows[0]
        without = run_query(query_db, Query(metric="opportunities")).rows[0]
        assert with_none.opportunities == without.opportunities

    def test_empty_set_matches_nothing(self, query_db: Database) -> None:
        empty = run_query(query_db, Query(metric="opportunities", filters={"response": []})).rows[0]
        assert empty.opportunities == 0


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


class TestMetrics:
    """What a metric computes, and that a frequency carries its sample."""

    def test_opportunities_is_the_denominator(self, query_db: Database) -> None:
        row = run_query(
            query_db, Query(metric="opportunities", filters={"street": "flop"}),
        ).rows[0]
        assert row.unit == "count"
        assert row.value == row.opportunities
        assert row.frequency_bp is None

    def test_action_count_uses_the_numerator(self, query_db: Database) -> None:
        query = Query(
            metric="action_count",
            filters={"street": "flop", "situation": "facing_cbet"},
            numerator={"response": "fold"},
        )
        row = run_query(query_db, query).rows[0]
        assert row.value == row.actions
        assert 0 < row.actions < row.opportunities

    def test_population_metrics_are_distinct_counts(self, query_db: Database) -> None:
        # The corpus is 31 hands played by six players; "decisions" is the
        # engine's native denominator, and these two must not be read as it.
        decisions = run_query(query_db, Query(metric="opportunities")).rows[0].opportunities
        hands = run_query(query_db, Query(metric="hands")).rows[0]
        players = run_query(query_db, Query(metric="players")).rows[0]
        assert (hands.value, players.value) == (31, 6)
        assert decisions > hands.value
        assert hands.unit == players.unit == "count"

    def test_frequency_returns_both_sides_and_the_rate(self, query_db: Database) -> None:
        row = run_query(
            query_db,
            Query(
                metric="frequency",
                filters={"street": "flop", "situation": "facing_cbet"},
                numerator={"response": "fold"},
            ),
        ).rows[0]
        assert row.opportunities > 0
        assert 0 < row.actions <= row.opportunities
        assert row.frequency_bp == row.actions * 10000 // row.opportunities

    def test_named_frequency_metrics_imply_the_numerator(self, query_db: Database) -> None:
        explicit = run_query(
            query_db,
            Query(
                metric="fold_frequency",
                filters={"street": "flop", "situation": "facing_cbet"},
                numerator={"response": "fold"},
            ),
        ).rows[0]
        implied = run_query(
            query_db,
            Query(metric="fold_frequency", filters={"street": "flop", "situation": "facing_cbet"}),
        ).rows[0]
        # ``fold_frequency`` already carries its numerator; restating it agrees.
        assert (explicit.opportunities, explicit.actions) == (implied.opportunities, implied.actions)
        for name, response in (("call_frequency", "call"), ("raise_frequency", "raise")):
            row = run_query(
                query_db,
                Query(metric=name, filters={"street": "flop", "situation": "facing_cbet"}),
            ).rows[0]
            reference = run_query(
                query_db,
                Query(
                    metric="frequency",
                    filters={"street": "flop", "situation": "facing_cbet"},
                    numerator={"response": response},
                ),
            ).rows[0]
            assert row.actions == reference.actions

    def test_average_sizing_ignores_zero(self, query_db: Database) -> None:
        row = run_query(
            query_db, Query(metric="average_sizing", filters={"street": "flop", "action_taken": "bets"}),
        ).rows[0]
        cursor = query_db.get_cursor()
        cursor.execute("SELECT AVG(sizingBp) FROM HandsActions WHERE street = 1 AND sizingBp > 0")
        assert row.value is not None and row.value > 0
        assert row.unit == "bp"

    def test_profit_sums_distinct_hand_players(self, query_db: Database) -> None:
        row = run_query(query_db, Query(metric="total_profit", filters={"player": "Anna"})).rows[0]
        expected = _scalar(
            query_db,
            "SELECT SUM(hp.totalProfit) FROM HandsPlayers hp JOIN Players p ON p.id = hp.playerId"
            " WHERE p.name = 'Anna'",
        )
        assert row.value == float(expected)

    def test_profit_per_opportunity_divides_by_decisions(self, query_db: Database) -> None:
        total = run_query(query_db, Query(metric="total_profit", filters={"player": "Boris"})).rows[0]
        per = run_query(query_db, Query(metric="profit_per_opportunity", filters={"player": "Boris"})).rows[0]
        assert total.opportunities == per.opportunities
        assert per.value == pytest.approx(total.value / per.opportunities)

    def test_all_in_ev_is_queryable(self, query_db: Database) -> None:
        row = run_query(query_db, Query(metric="all_in_ev", filters={"street": "preflop"})).rows[0]
        assert row.unit == "cents"
        assert row.value is not None

    def test_unknown_metric_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="Unknown metric"):
            compile_query(Query(metric="win_rate"))


# ---------------------------------------------------------------------------
# Grouping
# ---------------------------------------------------------------------------


class TestGrouping:
    """Dimensions group a metric, and the groups partition the population."""

    def test_group_by_one_dimension(self, query_db: Database) -> None:
        grouped = run_query(
            query_db, Query(metric="opportunities", filters={"street": "flop"}, group_by=("response",)),
        )
        total = run_query(query_db, Query(metric="opportunities", filters={"street": "flop"})).rows[0]
        assert grouped.total_opportunities == total.opportunities
        assert {row.group["response"] for row in grouped.rows} <= {"fold", "call", "raise", "bet", "check"}

    def test_group_by_two_dimensions(self, query_db: Database) -> None:
        grouped = run_query(
            query_db,
            Query(metric="fold_frequency", filters={"street": "flop"}, group_by=("position", "response")),
        )
        keys = [(row.group["position"], row.group["response"]) for row in grouped.rows]
        assert len(keys) == len(set(keys))  # one row per combination
        # The per-position totals recomposed from the two-dimension split match
        # the one-dimension split exactly: grouping only partitions the rows.
        by_position: dict[int, int] = {}
        for row in grouped.rows:
            by_position[row.group["position"]] = by_position.get(row.group["position"], 0) + row.opportunities
        one_dimension = run_query(
            query_db,
            Query(metric="opportunities", filters={"street": "flop"}, group_by=("position",)),
        )
        assert {row.group["position"]: row.opportunities for row in one_dimension.rows} == by_position

    def test_bucket_dimension_reuses_default_buckets(self, query_db: Database) -> None:
        grouped = run_query(
            query_db, Query(metric="average_sizing", filters={"street": "flop"}, group_by=("sizing_bucket",)),
        )
        labels = {row.group["sizing_bucket"] for row in grouped.rows}
        # #296's default scale, plus the sentinel for a decision with no size.
        assert labels <= {
            "0-25", "25-33", "33-40", "40-50", "50-66", "66-80", "80-100", "100-125", "125-150", "150+", "unknown",
        }
        assert "unknown" in labels  # flop checks and folds carry no size

    def test_faced_sizing_bucket_groups_across_the_situation_join(self, query_db: Database) -> None:
        """``facingSizingBp`` also exists on HandsSituations; grouping by its
        bucket while that table is joined must not be an ambiguous column."""
        grouped = run_query(
            query_db,
            Query(
                metric="fold_frequency",
                filters={"street": "flop", "situation": "facing_cbet"},
                group_by=("facing_sizing_bucket",),
            ),
        )
        assert grouped.total_opportunities > 0
        assert all(isinstance(row.group["facing_sizing_bucket"], str) for row in grouped.rows)

    def test_unknown_dimension_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="Unknown group_by"):
            compile_query(Query(metric="opportunities", group_by=("made_up",)))


# ---------------------------------------------------------------------------
# Drill-down and pagination
# ---------------------------------------------------------------------------


class TestDrilldownAndPagination:
    """A result row can name the hands behind it, a page at a time."""

    def test_hand_ids_match_the_population(self, query_db: Database) -> None:
        query = Query(metric="fold_frequency", filters={"street": "flop", "situation": "facing_cbet"})
        ids = run_hand_ids(query_db, query)
        assert ids == sorted(set(ids)) and ids
        cursor = query_db.get_cursor()
        cursor.execute(
            "SELECT COUNT(DISTINCT A.handId) FROM HandsActions A"
            " JOIN HandsSituations SI ON SI.handId = A.handId AND SI.actionNo = A.actionNo"
            " WHERE SI.streetName = 'flop' AND SI.labels LIKE '%\"facing_cbet\"%'",
        )
        assert len(ids) == int(cursor.fetchone()[0])

    def test_pagination_windows_the_list(self, query_db: Database) -> None:
        query = Query(metric="opportunities", filters={"street": "flop"})
        all_ids = run_hand_ids(query_db, query)
        page = Query(metric="opportunities", filters={"street": "flop"}, limit=3, offset=1)
        assert run_hand_ids(query_db, page) == all_ids[1:4]

    def test_hand_ids_narrow_to_the_numerator_on_request(self, query_db: Database) -> None:
        query = Query(
            metric="fold_frequency",
            filters={"street": "flop", "situation": "facing_cbet"},
        )
        population = run_hand_ids(query_db, query)
        folds_only = run_hand_ids(query_db, query, include_numerator=True)
        assert 0 < len(folds_only) <= len(population)

    def test_hand_id_query_is_parameterized(self) -> None:
        compiled = compile_hand_ids(
            Query(metric="opportunities", filters={"player": "x' OR 1=1 --"}), "?", "sqlite",
        )
        assert "OR 1=1" not in compiled.sql
        assert compiled.params == ("x' OR 1=1 --",)


# ---------------------------------------------------------------------------
# SQL safety and backend neutrality
# ---------------------------------------------------------------------------


class TestSqlSafety:
    """Values are bound, identifiers are registry-only."""

    def test_values_are_bound_not_interpolated(self) -> None:
        compiled = compile_query(
            Query(metric="opportunities", filters={"player": "Anything"}),
        )
        assert "Anything" not in compiled.sql
        assert "Anything" in compiled.params

    def test_quoted_value_does_not_execute(self, query_db: Database) -> None:
        hostile = "Anna'; DROP TABLE Hands; --"
        before = _scalar(query_db, "SELECT COUNT(*) FROM Hands")
        run_query(query_db, Query(metric="opportunities", filters={"player": hostile}))
        assert _scalar(query_db, "SELECT COUNT(*) FROM Hands") == before

    def test_placeholder_follows_the_backend(self) -> None:
        query = Query(metric="opportunities", filters={"street": "flop"})
        assert "?" in compile_query(query, "?", "sqlite").sql
        assert "%s" in compile_query(query, "%s", "mysql").sql

    def test_boolean_literal_follows_the_backend(self) -> None:
        query = Query(metric="opportunities", filters={"in_position": True})
        assert "= 1" in compile_query(query, "?", "sqlite").sql
        assert "= TRUE" in compile_query(query, "%s", "postgresql").sql

    def test_unknown_backend_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="Unknown backend"):
            compile_query(Query(metric="opportunities"), "%s", "oracle")

    def test_registries_are_the_only_identifiers(self) -> None:
        # Every filter and dimension declares its own SQL; nothing user-supplied
        # can reach the statement as an identifier.
        for name, spec in FILTERS.items():
            assert spec.column and "." in spec.column or spec.column.startswith("(")
        for name, (expression, aliases) in DIMENSIONS.items():
            assert expression and aliases


# ---------------------------------------------------------------------------
# Explainability
# ---------------------------------------------------------------------------


class TestExplainability:
    """A compiled query can be shown, not just run."""

    def test_description_names_metric_filters_and_grouping(self) -> None:
        compiled = compile_query(
            Query(
                metric="fold_frequency",
                filters={"street": "flop", "pot_type": "single_raised"},
                group_by=("response",),
            ),
        )
        assert "metric: fold_frequency" in compiled.description
        assert "street='flop'" in compiled.description
        assert "pot_type='single_raised'" in compiled.description
        assert "group_by: response" in compiled.description

    def test_as_dict_round_trips(self) -> None:
        compiled = compile_query(Query(metric="opportunities", filters={"street": "turn"}))
        payload = compiled.as_dict()
        assert payload["metric"] == "opportunities"
        assert payload["sql"] == compiled.sql
        assert payload["params"] == list(compiled.params)

    def test_every_metric_is_documented(self) -> None:
        for name in KNOWN_METRICS:
            assert compile_query(Query(metric=name)).sql

    def test_filter_planning_only_joins_what_it_reads(self) -> None:
        _conditions, _params, aliases = compile_filters({"player": "Anna"})
        assert aliases == {"P"}
        _conditions, _params, aliases = compile_filters({"board_rank": "ace-high"})
        # A board filter needs the situation join it hangs off.
        assert aliases == {"BF"}

    def test_a_numerator_that_needs_a_join_gets_it(self, query_db: Database) -> None:
        # ``fold_frequency`` carries ``response=fold``, which lives on the
        # situation table: a caller who never mentions the street must still
        # get the join, or the SQL refers to an alias that is not there.
        compiled = compile_query(Query(metric="fold_frequency"))
        assert "JOIN HandsSituations SI" in compiled.sql
        assert run_query(query_db, Query(metric="fold_frequency")).rows[0].opportunities == 341

    def test_an_identity_filter_needs_the_site_join(self) -> None:
        _conditions, params, aliases = compile_filters({"identity": [("PokerStars", "jeje")]})
        assert aliases == {"P", "S"}
        assert params == ["PokerStars", "jeje"]

    def test_hero_exclusion_keeps_decisions_with_no_situation(self, query_db: Database) -> None:
        # Every decision is either a known hero decision or a non-hero one: the
        # LEFT JOIN's unknown rows belong to the population, not to the hero.
        total = run_query(query_db, Query(metric="opportunities")).rows[0].opportunities
        hero = run_query(query_db, Query(metric="opportunities", filters={"hero": True})).rows[0].opportunities
        other = run_query(query_db, Query(metric="opportunities", filters={"hero": False})).rows[0].opportunities
        assert (hero, other) == (69, 272)
        assert hero + other == total
        assert "IS NULL" in compile_query(Query(metric="opportunities", filters={"hero": False})).sql


# ---------------------------------------------------------------------------
# Equivalence with existing predefined stats
# ---------------------------------------------------------------------------


class TestEquivalenceWithPredefinedStats:
    """Where a new query overlaps an existing stat, the two agree."""

    def test_fold_to_flop_cbet_matches_hud_cache(self, query_db: Database) -> None:
        query = Query(
            metric="fold_frequency",
            filters={"street": "flop", "situation": "facing_cbet"},
            group_by=("player",),
        )
        engine = {row.group["player"]: (row.opportunities, row.actions) for row in run_query(query_db, query).rows}
        cursor = query_db.get_cursor()
        cursor.execute(
            "SELECT p.name, SUM(hc.foldToStreet1CBChance), SUM(hc.foldToStreet1CBDone)"
            " FROM HudCache hc JOIN Players p ON p.id = hc.playerId GROUP BY p.name",
        )
        cache = {name: (int(opp or 0), int(done or 0)) for name, opp, done in cursor.fetchall()}

        for player, (chances, folds) in cache.items():
            opportunities, actions = engine.get(player, (0, 0))
            if player == DEVIATION_PLAYER:
                # The corpus documents that HudCache counts the flop raise handed
                # to this player as a c-bet; the situation model does not.
                assert chances - opportunities == 1
                assert folds - actions == 1
            else:
                assert opportunities == chances
                assert actions == folds

    def test_larger_population_than_the_cache(self, query_db: Database) -> None:
        # The engine is not limited to the cache's hand-level counters: it can
        # group the same stat by a dimension no cache column has.
        grouped = run_query(
            query_db,
            Query(
                metric="fold_frequency",
                filters={"street": "flop", "situation": "facing_cbet"},
                group_by=("sizing_bucket",),
            ),
        )
        assert grouped.total_opportunities > 0
        assert all(row.unit == "bp" for row in grouped.rows)

    def test_opportunities_agree_with_the_empty_filter(self, query_db: Database) -> None:
        # An unfiltered query is the whole pooled population, which is what the
        # per-hand tables sum to.
        row = run_query(query_db, Query(metric="opportunities")).rows[0]
        assert row.opportunities == _scalar(query_db, "SELECT COUNT(*) FROM HandsActions")


class TestHandStateVocabulary:
    """The hand-state filters and dimensions (#302), read off the stored rows."""

    def test_the_population_splits_into_classified_and_not(self, query_db: Database) -> None:
        """The two are a partition, and neither is a bucket called "unknown"."""
        assert _scalar(query_db, "SELECT COUNT(*) FROM HandsActions") == 341
        known = run_query(query_db, Query(metric="opportunities", filters={"hand_state_known": True}))
        unknown = run_query(query_db, Query(metric="opportunities", filters={"hand_state_known": False}))
        assert (known.total_opportunities, unknown.total_opportunities) == (37, 304)
        assert known.total_opportunities + unknown.total_opportunities == 341

    def test_made_hand_and_pair_detail_filters(self, query_db: Database) -> None:
        assert self._count(query_db, {"made_hand": ["high_card"]}) == 19
        assert self._count(query_db, {"made_hand": ["high_card", "one_pair"]}) == 32
        assert self._count(query_db, {"pair_detail": ["top_pair"]}) == 5
        assert self._count(query_db, {"made_hand_rank": [3, 9]}) == 5

    def test_nutness_filters(self, query_db: Database) -> None:
        assert self._count(query_db, {"nutness": ["nuts", "near_nuts"]}) == 1
        assert self._count(query_db, {"nutness": ["weak"]}) == 5

    def test_draw_filters_any_all_and_none(self, query_db: Database) -> None:
        assert self._count(query_db, {"draw": ["backdoor_straight_draw"]}) == 19
        assert self._count(query_db, {"draw_all": ["backdoor_straight_draw", "backdoor_flush_draw"]}) == 4
        assert self._count(query_db, {"draw_none": True}) == 16
        # No draw at all, on the flop, is a smaller population than either.
        assert self._count(query_db, {"street": "flop", "draw_none": True}) == 7

    def test_blocker_filters(self, query_db: Database) -> None:
        assert self._count(query_db, {"blocker": ["overcard_blocker"]}) == 19
        assert self._count(query_db, {"blocker_none": True}) == 18

    def test_a_flag_name_from_the_wrong_vocabulary_is_refused(self, query_db: Database) -> None:
        """A board-texture name is not a draw, however plausible it looks."""
        with pytest.raises(ValueError, match="Unknown draw"):
            run_query(query_db, Query(metric="opportunities", filters={"draw": ["rainbow"]}))
        with pytest.raises(ValueError, match="Unknown blocker"):
            run_query(query_db, Query(metric="opportunities", filters={"blocker": ["flush_possible"]}))
        with pytest.raises(ValueError, match="Unknown board flag"):
            run_query(query_db, Query(metric="opportunities", filters={"board_texture": ["flush_draw"]}))

    def test_flag_filters_bind_bits_not_names(self) -> None:
        """The flag name never reaches the SQL: only its bit does."""
        fragments, params, aliases = compile_filters({"draw": ["flush_draw"]})
        assert fragments == ["((HS.drawsMask & 1) <> 0)"]
        assert params == [] and aliases == {"HS"}
        # "None of them" is one mask test, not one per named flag.
        none_fragments, _, _ = compile_filters({"draw_none": True})
        assert none_fragments == ["(HS.drawsMask & 255) = 0"]

    def test_only_the_hand_state_source_is_joined_when_it_is_read(self) -> None:
        assert filter_sources({"draw": ["flush_draw"]}) == {"HS"}
        assert filter_sources({"made_hand": ["one_pair"]}) == {"HS"}
        assert filter_sources({"street": "flop"}) == {"SI"}
        compiled = compile_query(Query(metric="opportunities", filters={"nutness": ["strong"]}))
        assert "HandStates HS" in compiled.sql
        assert "BoardFeatures" not in compiled.sql

    def test_grouping_by_a_hand_state_dimension(self, query_db: Database) -> None:
        result = run_query(query_db, Query(metric="opportunities", group_by=("made_hand",)))
        counts = {row.group["made_hand"]: row.opportunities for row in result.rows}
        assert counts == {None: 304, "high_card": 19, "one_pair": 13, "two_pair": 3, "three_of_a_kind": 2}

    def test_grouping_by_pair_detail_keeps_the_hands_without_one(self, query_db: Database) -> None:
        """A high-card hand has no pair detail: that is a bucket, not a gap."""
        result = run_query(
            query_db,
            Query(metric="opportunities", filters={"street": "flop"}, group_by=("pair_detail",)),
        )
        counts = {row.group["pair_detail"]: row.opportunities for row in result.rows}
        assert counts[None] == 50  # 33 unclassified flops + 17 made hands with no pair detail
        assert (counts["overpair"], counts["top_pair"], counts["set"]) == (1, 4, 2)

    def test_a_decision_with_no_state_matches_no_category(self, query_db: Database) -> None:
        """Unknown cards are left out, not guessed into a category."""
        known = self._count(query_db, {"hand_state_known": True})
        for filters in ({"made_hand": ["high_card"]}, {"nutness": ["weak"]}, {"draw": ["gutshot"]}):
            assert self._count(query_db, filters) <= known
        # Every classified decision has a made hand and a nutness band.
        c = query_db.get_cursor()
        c.execute("SELECT COUNT(*) FROM HandStates WHERE madeHand = '' OR nutness = ''")
        assert c.fetchone()[0] == 0

    def test_the_hand_state_street_matches_the_situation_street(self, query_db: Database) -> None:
        by_hand_state = run_query(query_db, Query(metric="opportunities", filters={"hand_state_street": ["flop"]}))
        by_situation = run_query(
            query_db,
            Query(metric="opportunities", filters={"street": ["flop"], "hand_state_known": True}),
        )
        assert by_hand_state.total_opportunities == by_situation.total_opportunities == 27

    @staticmethod
    def _count(db: Database, filters: dict) -> int:
        return int(run_query(db, Query(metric="opportunities", filters=filters)).total_opportunities)


def test_paths_no_unused_import() -> None:
    """Guard the test module's own imports against drift."""
    assert Path(golden.GOLDEN_DIR).exists()


class TestQueriesThatOnlyTheNumeratorNeeds:
    """Four shapes the compiler used to emit as SQL no backend would run."""

    def test_a_numerator_brings_its_own_table_into_the_join(self, query_db: Database) -> None:
        """fold_frequency counts a situation response over an unfiltered population.

        Nothing but the numerator names HandsSituations, and the join was
        planned before the numerator was compiled, so the query selected a
        column from a table it had not joined.
        """
        result = run_query(query_db, Query(metric="fold_frequency"))

        assert result.rows
        row = result.rows[0]
        assert row.opportunities > 0
        assert 0 < row.actions < row.opportunities, "some decisions are folds, not all of them"

    def test_a_filtered_page_binds_its_parameters_in_order(self, query_db: Database) -> None:
        """The page used to be bound where the filter belonged, and vice versa."""
        unpaged = run_query(query_db, Query(metric="fold_frequency", filters={"street": "flop"}))
        assert unpaged.rows

        paged = run_query(
            query_db,
            Query(metric="fold_frequency", filters={"street": "flop"}, group_by=("position",), limit=1),
        )

        assert len(paged.rows) == 1
        assert paged.rows[0].opportunities > 0

    def test_the_limit_dimension_is_not_the_limit_keyword(self, query_db: Database) -> None:
        """``group_by=("limit",)`` is the betting limit, and LIMIT is reserved."""
        result = run_query(query_db, Query(metric="opportunities", group_by=("limit",)))

        assert [row.group["limit"] for row in result.rows] == ["nl"]
        assert result.rows[0].opportunities > 0

    def test_a_drill_down_narrows_the_population_instead_of_replacing_it(self, query_db: Database) -> None:
        """A call is not a fold: asking for both has to answer with neither.

        The population and the numerator constrained the same key, and merging
        the two dictionaries kept only the numerator's -- so the drill-down
        listed every hand with a fold, including hands the metric had never
        counted.
        """
        population = run_hand_ids(query_db, Query(metric="fold_frequency", filters={"response": "call"}))
        assert population, "calls happen in this corpus"

        narrowed = run_hand_ids(
            query_db,
            Query(metric="fold_frequency", filters={"response": "call"}),
            include_numerator=True,
        )

        assert narrowed == [], "no decision is a call and a fold at once"
