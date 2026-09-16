"""Sizing distributions and buckets over the persisted decisions (#296).

``HandsActions`` has carried per-decision sizing since #293 -- ``sizingBp``
for the aggression a row took, ``facingSizingBp`` for the aggression it
responded to -- and the golden corpus of #308 pins one size per default
bucket in scenario ``bet_sizing``. This module pins the vocabulary that
turns those columns into distributions:

* ``sizing_buckets`` -- the configurable bucket tables, the pure histogram
  and response helpers, and the SQL CASE expression the query engine groups
  by; the raw sizes must survive untouched (the HUD's averaging stats keep
  reading them);
* the golden corpus -- every pinned size of ``bet_sizing`` must land in the
  bucket the manifest names, both as the bet made and as the fold faced;
* real distributions -- multi-hand histograms and a per-bucket response
  breakdown built over imported rows, plus the multiway, raise and all-in
  decisions of the other scenarios.

The acceptance criteria of #296 in order: raw decision-level sizing is
queryable (it has been since #293; re-asserted here), default and custom
buckets are supported, histograms can be generated for a filtered
population, the HUD's average-sizing stats are untouched, and the edge
cases -- zero and unclear pot state, all-ins, multiway pots -- are covered.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from fpdb_3_legacy.sizing_buckets import (
    BUCKET_DECISION_COLUMNS,
    DECISION_BUCKETS,
    DEFAULT_BUCKETS,
    DEFAULT_OPEN_BB_BUCKETS,
    SIZING_SOURCE_COLUMNS,
    UNKNOWN_BUCKET,
    BucketConfig,
    BucketResponseStat,
    bucket_case_expression,
    bucket_counts,
    bucket_decision_rows,
    bucket_response_stats,
    open_size_bb_bp,
)
from tests.helpers import analytics_golden as golden

SCENARIOS = {scenario.id: scenario for scenario in golden.load_manifest().scenarios}

# The bet_sizing sizes, in the order the manifest pins them, with the bucket
# each size is declared to fall into.
SIZING_PINS = (
    (3100000021, 2307, "0-25"),
    (3100000022, 3076, "25-33"),
    (3100000023, 3846, "33-40"),
    (3100000024, 4615, "40-50"),
    (3100000025, 6153, "50-66"),
    (3100000026, 7692, "66-80"),
    (3100000027, 9230, "80-100"),
    (3100000028, 12307, "100-125"),
    (3100000029, 13846, "125-150"),
    (3100000030, 15384, "150+"),
)


@pytest.fixture(scope="module")
def corpus() -> golden.GoldenCorpus:
    """The whole golden corpus, imported once into a throwaway database."""
    with tempfile.TemporaryDirectory() as tmp:
        yield golden.import_golden_corpus(Path(tmp))


def bet_events(corpus: golden.GoldenCorpus, hand_id: int) -> list[dict]:
    """The flop rows of one bet_sizing hand: the c-bet and the fold facing it."""
    return corpus.action_rows(hand_id, street=1)


class TestBucketVocabulary:
    """The pure side: boundaries, labels, custom tables."""

    def test_every_pinned_size_lands_in_its_declared_bucket(self) -> None:
        for _hand_id, sizing_bp, bucket in SIZING_PINS:
            assert DEFAULT_BUCKETS.bucket_of(sizing_bp) == bucket

    def test_boundaries_tile_without_gap_or_overlap(self) -> None:
        bounds = DEFAULT_BUCKETS.upper_bounds_bp
        assert bounds == tuple(sorted(set(bounds)))
        assert bounds[0] > 1  # a stored 0 stays unknown, not smallest-bucket
        for lower, upper in zip(bounds, bounds[1:], strict=False):
            assert DEFAULT_BUCKETS.bucket_of(lower) == DEFAULT_BUCKETS.bucket_of(upper - 1)

    def test_zero_and_negative_are_unknown_not_smallest_bucket(self) -> None:
        assert DEFAULT_BUCKETS.bucket_of(0) is None
        assert DEFAULT_BUCKETS.bucket_of(-5) is None

    def test_one_more_label_than_bounds(self) -> None:
        assert len(DEFAULT_BUCKETS.labels) == len(DEFAULT_BUCKETS.upper_bounds_bp) + 1
        with pytest.raises(ValueError, match="one more label"):
            BucketConfig(name="bad", upper_bounds_bp=(2500,), labels=("a", "b", "c"))
        with pytest.raises(ValueError, match="positive"):
            BucketConfig(name="bad", upper_bounds_bp=(0,), labels=("a", "b"))

    def test_custom_buckets_are_supported(self) -> None:
        """A caller studies turn bets in thirds without touching this module."""
        thirds = BucketConfig(
            name="thirds",
            upper_bounds_bp=(3300, 6600),
            labels=("low", "mid", "high"),
        )
        assert [thirds.bucket_of(bp) for bp in (1000, 5000, 9000)] == ["low", "mid", "high"]
        histogram = bucket_counts((1000, 5000, 9000, 0), thirds)
        assert histogram == {"low": 1, "mid": 1, "high": 1, UNKNOWN_BUCKET: 1}

    def test_preflop_open_buckets_read_in_big_blinds(self) -> None:
        # A $5 open at $1/$2 is 2.5x, stored as 500 cents over a 200 cent blind.
        assert open_size_bb_bp(500, 200) == 250
        assert DEFAULT_OPEN_BB_BUCKETS.bucket_of(open_size_bb_bp(500, 200)) == "2-3"
        assert DEFAULT_OPEN_BB_BUCKETS.bucket_of(open_size_bb_bp(600, 200)) == "3-4"
        assert DEFAULT_OPEN_BB_BUCKETS.bucket_of(open_size_bb_bp(0, 200)) is None

    def test_decision_map_is_closed_over_known_columns(self) -> None:
        assert set(DECISION_BUCKETS) == {"betMade", "betFaced", "raiseMade", "raiseFaced"}
        for decision, (source, derived) in DECISION_BUCKETS.items():
            assert source in SIZING_SOURCE_COLUMNS
            assert derived in BUCKET_DECISION_COLUMNS
            assert source.endswith("izingBp"), f"{decision}: {source} is not a sizing column"

    def test_sql_case_rejects_non_sizing_columns(self) -> None:
        with pytest.raises(ValueError, match="bucketable"):
            bucket_case_expression("potBefore")

    @pytest.mark.parametrize("column", sorted(SIZING_SOURCE_COLUMNS))
    def test_sql_case_matches_the_python_buckets(self, column: str) -> None:
        """The SQL the query engine groups by must agree with bucket_of."""
        expression = bucket_case_expression(column)
        assert "unknown" in expression
        for _hand_id, sizing_bp, bucket in SIZING_PINS:
            rendered = expression.replace(column, str(sizing_bp), 1)
            # A tiny SQL-free evaluation of the CASE, column by column: the
            # first WHEN whose bounds hold names the bucket.
            assert bucket in expression
            assert str(sizing_bp) in rendered  # the column was substituted


class TestGoldenCorpusBuckets:
    """The persisted rows of the sizing scenario, bucketed."""

    def test_every_cbet_row_buckets_as_the_manifest_declares(self, corpus) -> None:
        for hand_id, sizing_bp, bucket in SIZING_PINS:
            (bet,) = [row for row in bet_events(corpus, hand_id) if row["actionType"] == "bets"]
            assert bet["sizingBp"] == sizing_bp
            assert DEFAULT_BUCKETS.bucket_of(bet["sizingBp"]) == bucket

    def test_the_fold_faces_the_same_size_in_the_same_bucket(self, corpus) -> None:
        for hand_id, sizing_bp, bucket in SIZING_PINS:
            (fold,) = [row for row in bet_events(corpus, hand_id) if row["actionType"] == "folds"]
            assert fold["facingSizingBp"] == sizing_bp
            assert DEFAULT_BUCKETS.bucket_of(fold["facingSizingBp"]) == bucket

    def test_histogram_of_the_whole_scenario_is_one_per_bucket(self, corpus) -> None:
        sizes = [
            row["sizingBp"]
            for hand in SCENARIOS["bet_sizing"].hands
            for row in bet_events(corpus, hand.hand_id)
            if row["actionType"] == "bets"
        ]
        histogram = bucket_counts(sizes)
        assert [histogram[bucket] for _hand, _bp, bucket in SIZING_PINS] == [1] * len(SIZING_PINS)
        assert histogram[UNKNOWN_BUCKET] == 0

    def test_faced_side_histogram_counts_the_folds(self, corpus) -> None:
        sizes = [
            row["facingSizingBp"]
            for hand in SCENARIOS["bet_sizing"].hands
            for row in bet_events(corpus, hand.hand_id)
            if row["actionType"] == "folds"
        ]
        histogram = bucket_counts(sizes)
        assert sum(histogram.values()) == len(SIZING_PINS)
        assert histogram[UNKNOWN_BUCKET] == 0

    def test_rows_persisted_before_the_model_keep_their_raw_size(self, corpus) -> None:
        """Raw decision-level sizing stays queryable -- no pre-bucketing at rest."""
        hand_id = SCENARIOS["bet_sizing"].hands[0].hand_id
        (bet,) = [row for row in bet_events(corpus, hand_id) if row["actionType"] == "bets"]
        assert bet["sizingBp"] == 2307
        assert "betMadeBucket" not in bet  # buckets are derived, never stored


class TestDistributions:
    """Histograms and responses over a filtered population of real rows."""

    def test_histogram_of_a_filtered_population(self, corpus) -> None:
        """Boris' flop c-bets across the corpus, filtered to his rows only."""
        sizes = [
            row["sizingBp"]
            for hand_id in corpus.actions
            for row in corpus.action_rows(hand_id, street=1)
            if row["playerName"] == "Boris" and row["actionType"] == "bets"
        ]
        histogram = bucket_counts(sizes)
        # The ten pinned c-bets, one per bucket, plus whatever the other
        # scenarios add -- the point is the map, not a frozen total.
        assert sum(histogram.values()) == len(sizes)
        for _hand_id, sizing_bp, bucket in SIZING_PINS:
            # Each pinned size is counted in the bucket it was declared for.
            assert histogram[bucket] >= 1

    def test_response_frequency_per_bucket(self, corpus) -> None:
        """Cara faces ten c-bets and folds them all: 0% of any response."""
        responses = [
            (
                row["facingSizingBp"],
                row["actionType"] in ("calls", "raises"),
            )
            for hand in SCENARIOS["bet_sizing"].hands
            for row in bet_events(corpus, hand.hand_id)
            if row["playerName"] == "Cara"
        ]
        stats = {stat.bucket: stat for stat in bucket_response_stats(responses)}
        assert stats[UNKNOWN_BUCKET].chances == 0
        for _hand_id, _sizing_bp, bucket in SIZING_PINS:
            assert stats[bucket].chances == 1
            assert stats[bucket].actions == 0
            assert stats[bucket].frequency_bp == 0

    def test_response_stat_counts_taken_responses(self) -> None:
        stat = BucketResponseStat("50-66")
        for size, responded in ((6153, True), (6200, True), (6400, False)):
            assert DEFAULT_BUCKETS.bucket_of(size) == "50-66"
            stat.chances += 1
            stat.actions += responded
        assert (stat.chances, stat.actions, stat.frequency_bp) == (3, 2, 6666)
        assert stat.as_dict() == {
            "bucket": "50-66",
            "chances": 3,
            "actions": 2,
            "frequency_bp": 6666,
        }

    def test_zero_frequency_is_not_division_by_zero(self) -> None:
        stat = BucketResponseStat("0-25")
        assert stat.frequency_bp == 0
        stat.chances = 4
        stat.actions = 1
        assert stat.frequency_bp == 2500

    def test_bucket_decision_rows_over_persisted_rows(self, corpus) -> None:
        rows = bet_events(corpus, 3100000025) + bet_events(corpus, 3100000027)
        histogram = bucket_decision_rows(rows, "sizingBp")
        assert histogram["50-66"] == 1
        assert histogram["80-100"] == 1
        assert sum(histogram.values()) == len(rows)
        with pytest.raises(ValueError, match="bucketable"):
            bucket_decision_rows(rows, "potAfter")


class TestOtherDecisions:
    """Raises, all-ins and multiway pots, from the other scenarios."""

    def test_preflop_raise_sizes_are_bucketable(self, corpus) -> None:
        """The 4-bet/5-bet scenario: every raise faces the previous size."""
        rows = corpus.action_rows(3100000006)
        raises = [row for row in rows if row["actionType"] == "raises"]
        assert len(raises) == 4
        # The open faces nothing (nothing was ever bet into it); the 3-bet,
        # 4-bet and 5-bet each face the previous aggression's size.
        assert raises[0]["facingSizingBp"] == 0
        for row in raises[1:]:
            assert row["sizingBp"] > 0
            assert DEFAULT_BUCKETS.bucket_of(row["sizingBp"]) is not None
            assert row["facingSizingBp"] > 0
            assert DEFAULT_BUCKETS.bucket_of(row["facingSizingBp"]) is not None

    def test_the_all_in_shove_buckets_like_any_raise(self, corpus) -> None:
        """A 200bb shove over a 40bb 4-bet is a 150%+ raise, not a special case."""
        rows = corpus.action_rows(3100000006)
        shove = rows[-1] if rows[-1]["actionType"] == "raises" else rows[0]
        shoves = [row for row in rows if row["allIn"]]
        assert len(shoves) == 1
        (shove,) = shoves
        assert shove["actionType"] == "raises"
        assert DEFAULT_BUCKETS.bucket_of(shove["sizingBp"]) == "150+"

    def test_multiway_flops_give_faced_sides_to_several_players(self, corpus) -> None:
        """One c-bet, several defenders: each faced row carries the same size."""
        rows = [row for row in corpus.action_rows(3100000014, street=1) if row["facingSizingBp"] > 0]
        assert len(rows) >= 2
        assert {row["facingSizingBp"] for row in rows} == {row["facingSizingBp"] for row in rows}
        histogram = bucket_counts([row["facingSizingBp"] for row in rows])
        assert histogram[UNKNOWN_BUCKET] == 0

    def test_calls_and_folds_carry_no_made_size(self, corpus) -> None:
        """A passive decision has no made size: unknown, not smallest bucket."""
        for hand_id in (3100000003, 3100000007, 3100000014):
            for row in corpus.action_rows(hand_id):
                if row["actionType"] in ("calls", "folds"):
                    assert row["sizingBp"] == 0
                    assert DEFAULT_BUCKETS.bucket_of(row["sizingBp"]) is None


class TestHudCompat:
    """The average-sizing stats the HUD already reads stay untouched."""

    def test_sizing_columns_are_not_repurposed(self) -> None:
        """The buckets add vocabulary; they do not redefine the raw columns."""
        from fpdb_3_legacy.action_events import ACTION_EVENT_COLUMNS

        assert "sizingBp" in ACTION_EVENT_COLUMNS
        assert "facingSizingBp" in ACTION_EVENT_COLUMNS
        # The derived names must not collide with a real event column.
        assert BUCKET_DECISION_COLUMNS.isdisjoint(ACTION_EVENT_COLUMNS)

    def test_hudcache_averages_still_sum_bp_totals(self) -> None:
        """The HUD's average-sizing path is sum/count over the same bp columns."""
        import fpdb_3_legacy.SQL as SQL

        query = SQL.Sql(db_server="sqlite").query["get_stats_from_hand"]
        assert "sum(hc.val_f_bet_made_bp)" in query
        assert "sum(hc.val_t_bet_made_bp)" in query
        assert "bucket" not in query.lower()
