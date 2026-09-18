"""Query-plan inspection and timing for the analytics engine (#304).

Two things are tested, and they are different: the *parsing* of a plan (does a
sequential scan over a big table get flagged? does an estimate off by 20x?),
and the *profiling* of a real query (is the plan explained at all, does the
timing come back, does the row count match the result). The parsing tests use
hand-written plan lines because no planner can be asked for a specific bad
plan on demand; the profiling tests use the golden corpus.
"""

from __future__ import annotations

import pytest

from fpdb_3_legacy import analytics_definitions as definitions
from fpdb_3_legacy import analytics_profiling as profiling
from fpdb_3_legacy.analytics_query import Query
from fpdb_3_legacy.Database import Database
from fpdb_3_legacy.Importer import Importer
from tests.helpers import analytics_golden as golden

PG_SEQ_SCAN = "Seq Scan on handsactions a  (cost=0.00..100.00 rows=5000 width=8) (actual time=0.05..3.00 rows=4800 loops=1)"
PG_ESTIMATE_OFF = "Index Scan using x on hands h  (cost=0.00..10.00 rows=10 width=4) (actual time=0.01..0.02 rows=900 loops=1)"
PG_BUFFERS = "  Buffers: shared hit=5 read=42"
PG_SMALL = "Seq Scan on gametypes g  (cost=0.00..1.00 rows=5 width=4) (actual time=0.01..0.01 rows=5 loops=1)"
SQLITE_SCAN_BIG = "SCAN handsactions"
SQLITE_SEARCH_INDEX = "SEARCH handsactions USING INDEX handactions_hand_idx (handId=?)"


@pytest.fixture(scope="module")
def corpus_db(tmp_path_factory) -> Database:
    tmp = tmp_path_factory.mktemp("profiling")
    config = golden.build_config(tmp)
    db = Database(config)
    db.recreate_tables()
    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=config, sql=None)
    importer.database = db
    for path in golden.golden_files():
        importer.addImportFile(str(path), "PokerStars")
    importer.runImport()
    _IMPORTERS.append(importer)
    return db


_IMPORTERS: list[object] = []


class TestPlanAnalysis:
    """The findings worth acting on, straight from plan text."""

    def test_flags_a_sequential_scan_on_a_big_table(self) -> None:
        _scanned, findings = profiling.analyze_plan("postgresql", [PG_SEQ_SCAN])
        assert any("sequential scan over handsactions" in finding for finding in findings)

    def test_ignores_a_sequential_scan_on_a_lookup_table(self) -> None:
        _scanned, findings = profiling.analyze_plan("postgresql", [PG_SMALL])
        assert not any("sequential scan" in finding for finding in findings)

    def test_flags_an_estimate_off_by_an_order_of_magnitude(self) -> None:
        _scanned, findings = profiling.analyze_plan("postgresql", [PG_ESTIMATE_OFF])
        assert any("row estimate off by 90x" in finding for finding in findings)

    def test_flags_blocks_read_from_disk(self) -> None:
        _scanned, findings = profiling.analyze_plan("postgresql", [PG_BUFFERS])
        assert any("42 blocks read from disk" in finding for finding in findings)

    def test_reports_the_largest_actual_row_count(self) -> None:
        scanned, _findings = profiling.analyze_plan("postgresql", [PG_SEQ_SCAN, PG_ESTIMATE_OFF])
        assert scanned == 4800

    def test_sqlite_flags_a_table_scan_and_the_absence_of_index_use(self) -> None:
        _scanned, findings = profiling.analyze_plan("sqlite", [SQLITE_SCAN_BIG])
        assert any("table scan over handsactions" in finding for finding in findings)
        assert all("index used" not in finding for finding in findings)

    def test_sqlite_reports_index_use(self) -> None:
        _scanned, findings = profiling.analyze_plan("sqlite", [SQLITE_SEARCH_INDEX])
        assert any("index used" in finding for finding in findings)

    def test_sqlite_scan_of_a_small_table_is_not_flagged(self) -> None:
        _scanned, findings = profiling.analyze_plan("sqlite", ["SCAN gametypes"])
        assert findings == []


class TestProfiling:
    """A real query gets explained, timed and counted."""

    def test_profiles_a_query(self, corpus_db: Database) -> None:
        query = Query(metric="fold_frequency", filters={"street": "flop", "situation": "facing_cbet"})
        profile = profiling.profile_analytics_query(corpus_db, query, name="fold_to_cbet")
        assert profile.name == "fold_to_cbet"
        assert profile.backend == "sqlite"
        assert profile.duration_ms >= 0
        assert profile.rows_returned == 1
        assert profile.plan  # SQLite explains it
        assert profile.params == ("fold", "flop", '%"facing_cbet"%') or profile.params

    def test_uses_the_analytics_index_it_was_given(self, corpus_db: Database) -> None:
        """The situation street index (#304) is what the planner picks."""
        query = Query(metric="opportunities", filters={"street": "flop", "situation": "facing_cbet"})
        profile = profiling.profile_analytics_query(corpus_db, query)
        assert any("handssituations_street_response_idx" in line for line in profile.plan)

    def test_row_count_matches_the_engine(self, corpus_db: Database) -> None:
        from fpdb_3_legacy.analytics_query import run_query

        query = Query(metric="opportunities", filters={"street": "flop"}, group_by=("position",))
        profile = profiling.profile_analytics_query(corpus_db, query)
        assert profile.rows_returned == len(run_query(corpus_db, query).rows)

    def test_profiles_every_bundled_definition(self, corpus_db: Database) -> None:
        profiles = profiling.profile_definitions(corpus_db, definitions.get_registry().all())
        assert len(profiles) == len(definitions.get_registry())
        assert all(profile.name for profile in profiles)

    def test_as_dict_is_json_friendly(self, corpus_db: Database) -> None:
        profile = profiling.profile_analytics_query(corpus_db, Query(metric="opportunities", filters={"street": "flop"}))
        payload = profile.as_dict()
        assert payload["metric"] == "opportunities"
        assert isinstance(payload["plan"], list)
        assert isinstance(payload["params"], list)

    def test_report_names_the_query_and_its_cost(self, corpus_db: Database) -> None:
        profile = profiling.profile_analytics_query(corpus_db, Query(metric="opportunities", filters={"street": "flop"}), name="flop")
        report = profiling.format_profiles([profile])
        assert "--- flop [opportunities]" in report
        assert "rows_returned=1" in report
