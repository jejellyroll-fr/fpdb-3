"""Hero-versus-Field drill-down: two sides, one narrowing, real hands (#366)."""

from __future__ import annotations

from pathlib import Path

import pytest

from fpdb_3_legacy.analytics_query import Query
from fpdb_3_legacy.Database import Database
from fpdb_3_legacy.Importer import Importer
from fpdb_3_legacy.research_browser import run_comparison
from fpdb_3_legacy.research_drilldown import (
    SIDE_FIELD,
    SIDE_HERO,
    DrillContext,
    count_side,
    counts_from_comparison_row,
    drill_counts,
    has_numerator,
    run_side_drill,
)
from fpdb_3_legacy.research_studies import builtin_studies
from fpdb_3_legacy.research_study_dashboard import StudyDashboardModel
from fpdb_3_legacy.research_study_explorer import StudyExplorerModel
from tests.helpers import analytics_golden as golden

_IMPORTERS: list[Importer] = []


@pytest.fixture(scope="module")
def golden_db(tmp_path_factory) -> Database:
    tmp = tmp_path_factory.mktemp("research-drilldown")
    config = golden.build_config(tmp)
    database = Database(config)
    database.recreate_tables()
    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=config, sql=None)
    importer.database = database
    for path in golden.golden_files():
        importer.addImportFile(str(path), "PokerStars")
    importer.runImport()
    _IMPORTERS.append(importer)
    return database


def _context(**filters) -> DrillContext:
    return DrillContext(
        query=Query(metric="fold_frequency", filters={"game": "holdem", **filters}),
        group={"street": "flop"},
    )


# -- the query contract --------------------------------------------------------


def test_both_sides_share_every_filter_but_the_population_identity() -> None:
    context = _context(hero=True)

    hero = context.side_query(SIDE_HERO)
    field = context.side_query(SIDE_FIELD)

    assert hero.filters["hero"] is True
    assert field.filters["hero"] is False
    assert {name: value for name, value in hero.filters.items() if name != "hero"} == {
        name: value for name, value in field.filters.items() if name != "hero"
    }
    assert context.sides_agree()


def test_a_row_group_narrows_both_sides_identically() -> None:
    context = _context()

    assert context.side_query(SIDE_HERO).filters["street"] == "flop"
    assert context.side_query(SIDE_FIELD).filters["street"] == "flop"


def test_a_visual_cross_filter_reaches_both_sides_unchanged() -> None:
    context = DrillContext(
        query=Query(metric="fold_frequency", filters={"game": "holdem"}),
        group={"position": "btn"},
        cross_filters={"board_pairing": "paired", "bet_size_bucket": "half_pot"},
    )

    for side in (SIDE_HERO, SIDE_FIELD):
        filters = context.side_query(side).filters
        assert filters["board_pairing"] == "paired"
        assert filters["bet_size_bucket"] == "half_pot"
        assert filters["position"] == "btn"
    assert context.sides_agree()


def test_numerator_mode_applies_the_same_metric_semantics_to_both_sides() -> None:
    context = _context()

    hero = context.side_query(SIDE_HERO, numerator_only=True)
    field = context.side_query(SIDE_FIELD, numerator_only=True)

    assert hero.metric == field.metric == "fold_frequency"
    assert hero.numerator == field.numerator
    assert context.sides_agree(numerator_only=True)
    assert has_numerator(hero) and has_numerator(field)


def test_a_context_that_already_picked_a_side_still_yields_two() -> None:
    hero_only = _context(hero=True)
    field_only = _context(hero=False)

    assert hero_only.side_query(SIDE_FIELD).filters["hero"] is False
    assert field_only.side_query(SIDE_HERO).filters["hero"] is True
    assert hero_only.row_filters() == field_only.row_filters()


def test_an_unknown_side_is_refused_rather_than_guessed() -> None:
    with pytest.raises(ValueError, match="Unknown drill side"):
        _context().side_query("villain")


def test_a_page_size_beyond_the_cap_is_refused(golden_db: Database) -> None:
    with pytest.raises(ValueError, match="page size"):
        run_side_drill(golden_db, _context(), SIDE_HERO, limit=10_000)
    with pytest.raises(ValueError, match="offset"):
        run_side_drill(golden_db, _context(), SIDE_HERO, offset=-1)


# -- the hands themselves ------------------------------------------------------


def test_each_side_returns_its_own_hands_and_never_a_merged_list(golden_db: Database) -> None:
    context = _context()

    hero = run_side_drill(golden_db, context, SIDE_HERO, limit=50)
    field = run_side_drill(golden_db, context, SIDE_FIELD, limit=50)

    assert hero.rows and field.rows
    assert hero.side == SIDE_HERO
    assert field.side == SIDE_FIELD
    hero_players = {row["playerName"] for row in hero.rows}
    field_players = {row["playerName"] for row in field.rows}
    assert len(hero_players) == 1  # The hero side is one player, by construction.
    assert not hero_players & field_players


def test_both_sides_match_the_comparison_samples_they_were_opened_from(golden_db: Database) -> None:
    preset = {
        "metric": "fold_frequency",
        "filters": {"game": "holdem"},
        "numerator": {},
        "group_by": ["street"],
    }
    comparison = run_comparison(golden_db, preset)
    row = next(row for row in comparison.rows if row.hero_opportunities and row.field_opportunities)
    context = DrillContext(
        query=Query(metric="fold_frequency", filters={"game": "holdem"}),
        group=dict(row.group),
    )

    displayed = counts_from_comparison_row(row)
    measured = drill_counts(golden_db, context)

    assert measured == displayed
    assert run_side_drill(golden_db, context, SIDE_HERO, limit=1).total_matches == row.hero_opportunities
    assert run_side_drill(golden_db, context, SIDE_FIELD, limit=1).total_matches == row.field_opportunities
    assert (
        run_side_drill(golden_db, context, SIDE_HERO, numerator_only=True, limit=1).total_matches
        == row.hero_actions
    )
    assert (
        run_side_drill(golden_db, context, SIDE_FIELD, numerator_only=True, limit=1).total_matches
        == row.field_actions
    )


def test_the_numerator_is_a_subset_of_the_population_on_both_sides(golden_db: Database) -> None:
    context = _context()

    for side in (SIDE_HERO, SIDE_FIELD):
        population = run_side_drill(golden_db, context, side, limit=200)
        numerator = run_side_drill(golden_db, context, side, numerator_only=True, limit=200)
        assert numerator.total_matches <= population.total_matches
        assert set(numerator.hand_ids) <= set(population.hand_ids)


def test_a_large_side_is_paged_rather_than_loaded_whole(golden_db: Database) -> None:
    context = _context()

    first = run_side_drill(golden_db, context, SIDE_FIELD, limit=5)
    second = run_side_drill(golden_db, context, SIDE_FIELD, limit=5, offset=5)

    assert len(first.hand_ids) == 5
    assert first.total_hands > 5
    assert first.has_more
    assert not first.has_previous
    assert second.has_previous
    assert not set(first.hand_ids) & set(second.hand_ids)
    assert "of " in first.page_note


def test_paging_walks_the_whole_side_without_gaps_or_repeats(golden_db: Database) -> None:
    context = _context()
    seen: list[int] = []
    offset = 0
    while True:
        page = run_side_drill(golden_db, context, SIDE_HERO, limit=25, offset=offset)
        seen.extend(page.hand_ids)
        if not page.has_more:
            break
        offset += page.limit

    assert len(seen) == len(set(seen))
    assert len(seen) == run_side_drill(golden_db, context, SIDE_HERO, limit=1).total_hands


def test_unknown_cards_stay_unknown_and_the_coverage_is_stated(golden_db: Database) -> None:
    context = _context()

    field = run_side_drill(golden_db, context, SIDE_FIELD, limit=100)

    assert field.known_cards + field.unknown_cards == len(field.rows)
    assert all(row["playerCards"] == "" or len(row["playerCards"]) == 4 for row in field.rows)
    assert field.card_coverage_note
    if field.unknown_cards:
        assert "never recorded" in field.card_coverage_note


def test_an_empty_side_is_an_empty_page_rather_than_an_error(golden_db: Database) -> None:
    context = DrillContext(
        query=Query(metric="fold_frequency", filters={"game": "razz"}),
        group={},
    )

    page = run_side_drill(golden_db, context, SIDE_FIELD)

    assert page.rows == ()
    assert page.total_hands == 0
    assert not page.has_more
    assert "No hands" in page.page_note


# -- the study integration -----------------------------------------------------


def _dashboard(tmp_path: Path) -> StudyDashboardModel:
    explorer = StudyExplorerModel(builtin_studies(), tmp_path / "history.json")
    selection = explorer.open_study(
        "srp_pfr_ip_flop",
        context_filters={"game": "holdem", "hero": True},
        remember=False,
    )
    return StudyDashboardModel(selection)


def test_a_study_panel_drills_into_the_population_it_displayed(tmp_path: Path) -> None:
    dashboard = _dashboard(tmp_path)

    context = dashboard.drill_context("overview")

    assert context.side_query(SIDE_HERO).filters == dashboard.side_query("overview", True).filters
    assert context.side_query(SIDE_FIELD).filters == dashboard.side_query("overview", False).filters
    assert context.sides_agree()


def test_a_study_cross_filter_reaches_both_sides_of_the_drill(tmp_path: Path) -> None:
    dashboard = _dashboard(tmp_path)
    dashboard.add_cross_filter("board_pairing", "paired", "Paired boards")

    context = dashboard.drill_context("board")

    for side in (SIDE_HERO, SIDE_FIELD):
        assert context.side_query(side).filters["board_pairing"] == "paired"
    assert context.sides_agree()


def test_every_study_panel_offers_a_drill_context(tmp_path: Path) -> None:
    dashboard = _dashboard(tmp_path)

    for panel_id in dashboard.panel_ids():
        context = dashboard.drill_context(panel_id)
        assert context.sides_agree()
        assert context.label


def test_study_drill_counts_match_the_panel_population(golden_db: Database, tmp_path: Path) -> None:
    dashboard = _dashboard(tmp_path)
    context = dashboard.drill_context("overview")

    hero = count_side(golden_db, context, SIDE_HERO)
    field = count_side(golden_db, context, SIDE_FIELD)
    page = run_side_drill(golden_db, context, SIDE_HERO, limit=10)

    assert hero >= 0
    assert field >= 0
    assert page.total_matches == hero


def test_a_biggest_differences_deep_link_keeps_both_sides_of_the_drill(tmp_path: Path) -> None:
    """The route fpdb takes from a difference row: panel, then cross-filters."""
    explorer = StudyExplorerModel(builtin_studies(), tmp_path / "history.json")
    selection = explorer.open_study("srp_defender_oop_flop", remember=False)
    dashboard = StudyDashboardModel(selection)
    dashboard.set_active_panel("overview")
    dashboard.add_cross_filter("response", "fold", "Response: fold")

    context = dashboard.drill_context()

    assert context.side_query(SIDE_HERO).filters["response"] == "fold"
    assert context.side_query(SIDE_FIELD).filters["response"] == "fold"
    assert context.sides_agree()
    assert "Response: fold" in context.label
