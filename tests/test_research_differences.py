"""Hero-versus-Field discovery contract for Study Explorer (#365)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from fpdb_3_legacy.Database import Database
from fpdb_3_legacy.Importer import Importer
from fpdb_3_legacy.research_differences import (
    DifferenceFilters,
    build_difference_report,
    curated_difference_candidates,
)
from fpdb_3_legacy.research_studies import StudyPanelSpec, StudyRegistry, StudySpec, builtin_studies
from tests.helpers import analytics_golden as golden

_IMPORTERS: list[Importer] = []


@pytest.fixture
def golden_db(tmp_path: Path) -> Database:
    config = golden.build_config(tmp_path)
    database = Database(config)
    database.recreate_tables()
    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=config, sql=None)
    importer.database = database
    for path in golden.golden_files():
        importer.addImportFile(str(path), "PokerStars")
    importer.runImport()
    _IMPORTERS.append(importer)
    return database


def test_candidates_are_curated_grouped_frequency_panels_only() -> None:
    candidates = curated_difference_candidates(builtin_studies())

    assert candidates
    assert all(candidate.panel_kind in {"frequency", "response_distribution"} for candidate in candidates)
    assert not any(candidate.panel_kind == "sizing_distribution" for candidate in candidates)
    assert len({candidate.id for candidate in candidates}) == len(candidates)


def test_report_ranks_real_hero_field_gaps_and_keeps_the_drill_context(golden_db: Database) -> None:
    report = build_difference_report(
        golden_db,
        builtin_studies(),
        DifferenceFilters(min_hero_sample=0, min_field_sample=0, max_rows=10),
    )

    assert report.rows
    assert report.panels_executed == report.candidates_evaluated
    assert all(row.hero_sample > 0 and row.field_sample > 0 for row in report.rows)
    assert all(row.unit == "frequency" for row in report.rows)
    assert all(row.score == abs(row.gap_bp) * min(row.hero_sample, row.field_sample) for row in report.rows)
    assert report.rows[0].score >= report.rows[-1].score
    assert "not EV loss" in report.heuristic_description
    assert any(row.cross_filters or row.focus_filters for row in report.rows)
    assert any(row.focus_filters for row in report.rows)


def test_response_difference_keeps_the_distribution_denominator_for_the_dashboard(
    golden_db: Database,
) -> None:
    report = build_difference_report(
        golden_db,
        builtin_studies(),
        DifferenceFilters(min_hero_sample=0, min_field_sample=0, max_rows=100),
    )

    response_rows = [row for row in report.rows if row.focus_filters]
    assert response_rows
    assert all(not row.cross_filters for row in response_rows)
    assert all("response" in row.focus_filters for row in response_rows)


def test_response_difference_keeps_zero_response_bins_in_the_ranking(monkeypatch) -> None:
    study = StudySpec(
        id="response_only",
        title="Response only",
        path=("preflop",),
        base_filters={"game": "holdem"},
        variables=(),
        panels=(
            StudyPanelSpec(
                "responses",
                "Responses",
                "response_distribution",
                group_by=("response",),
            ),
        ),
    )
    registry = StudyRegistry((study,))

    class FakeResult:
        def __init__(self, response: str) -> None:
            self.rows = [SimpleNamespace(group={"response": response}, opportunities=10)]
            self.total_opportunities = 10

    import fpdb_3_legacy.research_differences as differences

    monkeypatch.setattr(
        differences,
        "_execute_side",
        lambda _db, _compiled, hero: FakeResult("fold" if hero else "call"),
    )

    report = differences.build_difference_report(
        object(),
        registry,
        DifferenceFilters(min_hero_sample=0, min_field_sample=0),
    )

    by_response = {row.context: row for row in report.rows}
    assert by_response["Response: Fold"].field_value_bp == 0
    assert by_response["Response: Call"].hero_value_bp == 0
    assert by_response["Response: Fold"].field_sample == 10
    assert by_response["Response: Call"].hero_sample == 10


def test_sample_controls_can_hide_small_groups_without_changing_the_candidate_set(golden_db: Database) -> None:
    report = build_difference_report(
        golden_db,
        builtin_studies(),
        DifferenceFilters(min_hero_sample=20, min_field_sample=20, max_rows=10),
    )

    assert not report.rows
    assert report.low_sample_groups > 0
    assert report.candidates_evaluated == len(curated_difference_candidates(builtin_studies()))
