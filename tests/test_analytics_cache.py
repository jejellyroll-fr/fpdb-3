"""Incremental aggregate cache: correctness, increment and invalidation (#304).

The cache exists to make repeated analytics cheap without ever answering a
question the direct query would answer differently. The tests are therefore
in two halves:

* **Equivalence** -- for every cacheable metric, the cached result and the
  direct query agree, grouped and ungrouped. The average metrics are checked
  too, on the other side: they are *not* cached, and the bypass returns the
  same answer.
* **Lifecycle** -- a refresh after new hands adds only the delta and the
  result still matches; a version change and a stale classification each drop
  the cache and rebuild it; an explicit invalidation empties it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fpdb_3_legacy import analytics_benchmark as benchmark
from fpdb_3_legacy import analytics_cache as cache
from fpdb_3_legacy import analytics_lifecycle as lifecycle
from fpdb_3_legacy.analytics_query import Query, run_query
from fpdb_3_legacy.Database import Database
from fpdb_3_legacy.Importer import Importer
from tests.helpers import analytics_golden as golden


@pytest.fixture
def corpus_db(tmp_path: Path) -> Database:
    """A fresh corpus import per test: these tests mutate the cache."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    config = golden.build_config(tmp_path)
    db = Database(config)
    db.recreate_tables()
    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=config, sql=None)
    importer.database = db
    for path in golden.golden_files():
        importer.addImportFile(str(path), "PokerStars")
    importer.runImport()
    _IMPORTERS.append(importer)
    yield db
    db.disconnect()


_IMPORTERS: list[object] = []


def _pairs(result) -> list[dict]:
    return [row.as_dict() for row in result.rows]


CACHEABLE_QUERIES = (
    Query(metric="opportunities", filters={"street": "flop"}),
    Query(metric="action_count", filters={"street": "flop"}, numerator={"action_taken": "bets"}),
    Query(metric="fold_frequency", filters={"street": "flop", "situation": "facing_cbet"}, group_by=("position",)),
    Query(metric="frequency", filters={"street": "preflop"}, numerator={"action_taken": "folds"}, group_by=("position",)),
    Query(metric="total_profit", filters={"player": "Anna"}),
    Query(metric="profit_per_opportunity", filters={"street": "preflop"}),
    Query(metric="all_in_ev", filters={"street": "preflop"}),
    Query(metric="ev_per_opportunity", filters={"street": "preflop"}, group_by=("player",)),
)


class TestEquivalence:
    """A cached answer is the direct answer."""

    @pytest.mark.parametrize("query", CACHEABLE_QUERIES)
    def test_cached_matches_direct(self, corpus_db: Database, query: Query) -> None:
        direct = _pairs(run_query(corpus_db, query))
        cached = _pairs(cache.cached_query(corpus_db, query))
        assert cached == direct

    def test_average_metrics_bypass_the_cache(self, corpus_db: Database) -> None:
        query = Query(metric="average_sizing", filters={"street": "flop"}, group_by=("sizing_bucket",))
        assert cache.is_cacheable(query) is False
        cache.cached_query(corpus_db, query)
        # Nothing was written for it.
        assert cache.aggregate_stats(corpus_db).rows == 0
        assert _pairs(cache.cached_query(corpus_db, query)) == _pairs(run_query(corpus_db, query))

    def test_cacheable_metrics_are_the_additive_ones(self) -> None:
        assert "frequency" in cache.cache_metrics()
        assert "total_profit" in cache.cache_metrics()
        for metric in cache.NON_CACHEABLE_METRICS:
            assert metric not in cache.cache_metrics()

    def test_fingerprint_is_order_independent(self) -> None:
        a = Query(metric="opportunities", filters={"street": "flop", "player": "Anna"})
        b = Query(metric="opportunities", filters={"player": "Anna", "street": "flop"})
        assert cache.query_fingerprint(a) == cache.query_fingerprint(b)

    def test_fingerprint_separates_different_queries(self) -> None:
        a = Query(metric="opportunities", filters={"street": "flop"})
        b = Query(metric="opportunities", filters={"street": "turn"})
        c = Query(metric="fold_frequency", filters={"street": "flop"})
        assert len({cache.query_fingerprint(a), cache.query_fingerprint(b), cache.query_fingerprint(c)}) == 3

    def test_pagination_does_not_change_the_fingerprint(self) -> None:
        base = Query(metric="opportunities", filters={"street": "flop"})
        paged = Query(metric="opportunities", filters={"street": "flop"}, limit=10, offset=20)
        assert cache.query_fingerprint(base) == cache.query_fingerprint(paged)

    def test_range_endpoint_order_changes_the_fingerprint(self) -> None:
        maximum = Query(metric="opportunities", filters={"big_blind": [None, 100]})
        minimum = Query(metric="opportunities", filters={"big_blind": [100, None]})
        assert cache.query_fingerprint(maximum) != cache.query_fingerprint(minimum)

    def test_paged_and_unpaged_reads_share_complete_counters(self, corpus_db: Database) -> None:
        base = Query(metric="opportunities", filters={"street": "preflop"}, group_by=("position",))
        paged = Query(metric=base.metric, filters=base.filters, group_by=base.group_by, limit=1)
        unpaged = _pairs(run_query(corpus_db, base))

        # Whichever form populates the entry first must not change the other.
        first_page = _pairs(cache.cached_query(corpus_db, paged))
        assert first_page == unpaged[:1]
        assert _pairs(cache.cached_query(corpus_db, base)) == unpaged


class TestIncrement:
    """New hands are absorbed by the delta, not by a rebuild."""

    def test_new_hands_are_absorbed(self, corpus_db: Database) -> None:
        query = Query(metric="fold_frequency", filters={"street": "flop", "situation": "facing_cbet"}, group_by=("position",))
        cache.cached_query(corpus_db, query)
        watermark_before = max(cache.aggregate_stats(corpus_db).watermarks.values())
        assert watermark_before == 30

        benchmark.synthesize_hands(corpus_db, 5)

        cached = _pairs(cache.cached_query(corpus_db, query))
        assert cached == _pairs(run_query(corpus_db, query))
        watermark_after = max(cache.aggregate_stats(corpus_db).watermarks.values())
        assert watermark_after == 35

    def test_repeated_reads_do_not_change_the_answer(self, corpus_db: Database) -> None:
        query = Query(metric="opportunities", filters={"street": "flop"})
        first = _pairs(cache.cached_query(corpus_db, query))
        second = _pairs(cache.cached_query(corpus_db, query))
        assert first == second

    def test_grouped_counters_accumulate_per_group(self, corpus_db: Database) -> None:
        query = Query(metric="opportunities", filters={"street": "preflop"}, group_by=("position",))
        before = {row["position"]: row["opportunities"] for row in _pairs(cache.cached_query(corpus_db, query))}
        benchmark.synthesize_hands(corpus_db, 3)
        after_direct = {row["position"]: row["opportunities"] for row in _pairs(run_query(corpus_db, query))}
        after_cached = {row["position"]: row["opportunities"] for row in _pairs(cache.cached_query(corpus_db, query))}
        assert after_cached == after_direct
        assert all(after_direct[key] >= before.get(key, 0) for key in after_direct)


class TestInvalidation:
    """Every reason the counters could lie drops them."""

    def test_explicit_invalidation_empties_the_cache(self, corpus_db: Database) -> None:
        cache.cached_query(corpus_db, Query(metric="opportunities", filters={"street": "flop"}))
        assert cache.aggregate_stats(corpus_db).rows > 0
        removed = cache.invalidate_aggregates(corpus_db, "test")
        assert removed > 0
        assert cache.aggregate_stats(corpus_db).rows == 0

    def test_version_change_forces_a_rebuild(self, corpus_db: Database) -> None:
        query = Query(metric="opportunities", filters={"street": "flop"})
        cache.cached_query(corpus_db, query)
        cursor = corpus_db.get_cursor()
        cursor.execute("UPDATE AnalyticsMeta SET value = '0' WHERE name = 'aggregate_version'")
        corpus_db.commit()
        assert cache.aggregate_stats(corpus_db).version == 0
        assert _pairs(cache.cached_query(corpus_db, query)) == _pairs(run_query(corpus_db, query))
        assert cache.aggregate_stats(corpus_db).version == cache.ANALYTICS_CACHE_VERSION

    def test_stale_classification_forces_a_rebuild(self, corpus_db: Database) -> None:
        query = Query(metric="opportunities", filters={"street": "flop"})
        cache.cached_query(corpus_db, query)
        cursor = corpus_db.get_cursor()
        cursor.execute("DELETE FROM AnalyticsMeta WHERE name = 'board_features_version'")
        corpus_db.commit()
        assert "board_features" in lifecycle.stale_subsystems(corpus_db)
        assert _pairs(cache.cached_query(corpus_db, query)) == _pairs(run_query(corpus_db, query))

    def test_force_recomputes_a_full_result(self, corpus_db: Database) -> None:
        query = Query(metric="fold_frequency", filters={"street": "flop"}, group_by=("response",))
        cache.cached_query(corpus_db, query)
        benchmark.synthesize_hands(corpus_db, 2)
        forced = _pairs(cache.cached_query(corpus_db, query, force=True))
        assert forced == _pairs(run_query(corpus_db, query))

    def test_delta_and_watermark_roll_back_together(self, corpus_db: Database, monkeypatch) -> None:
        query = Query(metric="opportunities", filters={"street": "flop"})
        cache.cached_query(corpus_db, query)
        before = _pairs(cache.cached_query(corpus_db, query))
        watermark = cache.aggregate_stats(corpus_db).watermarks[cache.query_fingerprint(query)]
        benchmark.synthesize_hands(corpus_db, 1)

        original = cache._write_meta

        def fail_after_delta(db, name, value, commit=True):
            if name.startswith(cache._WATERMARK_PREFIX):
                raise RuntimeError("metadata write failed")
            return original(db, name, value, commit)

        monkeypatch.setattr(cache, "_write_meta", fail_after_delta)
        with pytest.raises(RuntimeError, match="metadata write failed"):
            cache.cached_query(corpus_db, query)

        monkeypatch.undo()
        assert cache.aggregate_stats(corpus_db).watermarks[cache.query_fingerprint(query)] == watermark
        assert _pairs(cache.cached_query(corpus_db, query)) == _pairs(run_query(corpus_db, query))
        # The failed refresh was rolled back; the next successful refresh is
        # still allowed to consume the new hand exactly once.
        assert cache.aggregate_stats(corpus_db).watermarks[cache.query_fingerprint(query)] > watermark


def test_stats_report_is_json_friendly(corpus_db: Database) -> None:
    cache.cached_query(corpus_db, Query(metric="opportunities", filters={"street": "flop"}))
    payload = cache.aggregate_stats(corpus_db).as_dict()
    assert payload["version"] == cache.ANALYTICS_CACHE_VERSION
    assert payload["queries"] == 1
    assert payload["watermarks"]
