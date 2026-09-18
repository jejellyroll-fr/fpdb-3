"""Reproducible analytics benchmarks: the dataset and the harness (#304).

The benchmark suite is only worth anything if it is reproducible and if the
generated dataset is a real one -- same joins, same per-hand cardinality, not
an empty table that makes every query instant. The tests assert exactly that:
the generator clones every analytics table of the source hand, the result is
deterministic, and the harness times the query shapes and reports them against
their targets.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fpdb_3_legacy import analytics_benchmark as benchmark
from fpdb_3_legacy.analytics_query import Query
from fpdb_3_legacy.Database import Database
from fpdb_3_legacy.Importer import Importer
from tests.helpers import analytics_golden as golden


@pytest.fixture
def corpus_db(tmp_path: Path) -> Database:
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


def _count(db: Database, table: str, where: str = "1=1") -> int:
    cursor = db.get_cursor()
    cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}")  # nosec B608  # nosemgrep
    return int(cursor.fetchone()[0])


class TestSynthesis:
    """The generated dataset has the shape of real data."""

    def test_creates_the_requested_hands(self, corpus_db: Database) -> None:
        before = _count(corpus_db, "Hands")
        created = benchmark.synthesize_hands(corpus_db, 7)
        assert created == 7
        assert _count(corpus_db, "Hands") == before + 7

    def test_clones_the_analytics_tables(self, corpus_db: Database) -> None:
        source = benchmark._source_hand(corpus_db, None)
        counts_before = {table: _count(corpus_db, table) for table in benchmark.CLONED_TABLES}
        assert all(counts_before[table] > 0 for table in ("HandsPlayers", "HandsActions", "BoardFeatures", "HandsSituations"))
        benchmark.synthesize_hands(corpus_db, 5, source)
        for table in benchmark.CLONED_TABLES:
            per_hand = _count(corpus_db, table, f"handId = {source}")
            if per_hand:
                # Each clone carries exactly the source hand's rows for the table.
                cursor = corpus_db.get_cursor()
                cursor.execute(  # nosec B608  # nosemgrep
                    f"SELECT handId, COUNT(*) FROM {table} GROUP BY handId ORDER BY handId DESC LIMIT 5",
                )
                per_clone = {row[1] for row in cursor.fetchall()}
                assert per_clone == {per_hand}
                assert _count(corpus_db, table) > counts_before[table]

    def test_site_hand_numbers_stay_unique(self, corpus_db: Database) -> None:
        benchmark.synthesize_hands(corpus_db, 10)
        cursor = corpus_db.get_cursor()
        cursor.execute("SELECT COUNT(siteHandNo), COUNT(DISTINCT siteHandNo) FROM Hands")
        total, distinct = cursor.fetchone()
        assert total == distinct

    def test_generation_is_deterministic(self, corpus_db: Database) -> None:
        """Same source hand, same rows: every generation adds the same amount."""
        source = benchmark._source_hand(corpus_db, None)
        before = _count(corpus_db, "HandsActions")
        benchmark.synthesize_hands(corpus_db, 4, source)
        after_first = _count(corpus_db, "HandsActions")
        benchmark.synthesize_hands(corpus_db, 4, source)
        after_second = _count(corpus_db, "HandsActions")
        assert after_first - before == after_second - after_first > 0

    def test_zero_hands_is_a_no_op(self, corpus_db: Database) -> None:
        before = _count(corpus_db, "Hands")
        assert benchmark.synthesize_hands(corpus_db, 0) == 0
        assert _count(corpus_db, "Hands") == before

    def test_empty_database_is_refused(self, tmp_path: Path) -> None:
        config = golden.build_config(tmp_path)
        db = Database(config)
        db.recreate_tables()
        with pytest.raises(ValueError, match="no hands"):
            benchmark.synthesize_hands(db, 1)
        db.disconnect()


class TestHarness:
    """The harness times the shapes the issue names."""

    def test_times_every_default_benchmark(self, corpus_db: Database) -> None:
        results = benchmark.benchmark_queries(corpus_db, repeats=1)
        assert [result.name for result in results] == [name for name, _query in benchmark.DEFAULT_BENCHMARKS]
        assert all(result.best_ms >= 0 for result in results)
        assert all(result.repeats == 1 for result in results)

    def test_targets_cover_the_benchmarks(self) -> None:
        assert set(benchmark.LATENCY_TARGETS_MS) == {name for name, _query in benchmark.DEFAULT_BENCHMARKS}

    def test_a_clock_is_injectable(self, corpus_db: Database) -> None:
        # One empty-result query, two repeats: four ticks.
        ticks = iter([0.0, 0.010, 1.0, 1.030])
        query = Query(metric="opportunities", filters={"hand_id": -1})
        results = benchmark.benchmark_queries(corpus_db, queries=[("only", query)], repeats=2, clock=lambda: next(ticks))
        assert results[0].best_ms == pytest.approx(10.0)
        assert results[0].mean_ms == pytest.approx(20.0)
        assert results[0].within_target

    def test_report_is_a_table_with_targets(self, corpus_db: Database) -> None:
        report = benchmark.format_results(benchmark.benchmark_queries(corpus_db, repeats=1))
        assert "benchmark" in report
        assert "filtered_frequency" in report
        assert "yes" in report or "NO" in report

    def test_result_serializes(self, corpus_db: Database) -> None:
        results = benchmark.benchmark_queries(corpus_db, repeats=1)
        payload = results[0].as_dict()
        assert payload["name"] and payload["repeats"] == 1
        assert "within_target" in payload
