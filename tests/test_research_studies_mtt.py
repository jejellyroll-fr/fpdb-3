"""The MTT study pack, against a deterministic tournament corpus (#369)."""

from __future__ import annotations

import pytest

from fpdb_3_legacy.analytics_query import Query, run_query
from fpdb_3_legacy.Database import Database
from fpdb_3_legacy.Importer import Importer
from fpdb_3_legacy.research_studies import builtin_studies, execute_panel
from fpdb_3_legacy.research_study_dashboard import StudyDashboardModel
from fpdb_3_legacy.research_study_explorer import StudyExplorerModel
from fpdb_3_legacy.stack_depth_buckets import (
    DEFAULT_MTT_STACKS,
    STACK_DEPTH_BUCKETS,
    UNKNOWN_STACK_BUCKET,
    StackDepthBuckets,
    mixes_stack_depths,
    stack_bucket_of,
)
from tests.helpers import mtt_golden as mtt

_IMPORTERS: list[Importer] = []
MTT_STUDIES = tuple(
    study for study in builtin_studies().studies if study.tournament is True
)
STACK_DIMENSION = "effective_stack_bucket"


@pytest.fixture(scope="module")
def mtt_db(tmp_path_factory) -> Database:
    config = mtt.build_config(tmp_path_factory.mktemp("mtt-studies"))
    database = Database(config)
    database.recreate_tables()
    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=config, sql=None)
    importer.database = database
    for path in mtt.mtt_files():
        importer.addImportFile(str(path), "PokerStars")
    importer.runImport()
    _IMPORTERS.append(importer)
    return database


# -- the bands -----------------------------------------------------------------


def test_the_bands_read_the_way_a_tournament_player_says_them() -> None:
    # The column is hundredths of a big blind, and the bounds are inclusive.
    assert stack_bucket_of(900) == "under_10"
    assert stack_bucket_of(1000) == "under_10"
    assert stack_bucket_of(1001) == "10_to_15"
    assert stack_bucket_of(2500) == "15_to_25"
    assert stack_bucket_of(4000) == "25_to_40"
    assert stack_bucket_of(6000) == "40_to_60"
    assert stack_bucket_of(10000) == "60_to_100"
    assert stack_bucket_of(10001) == "100_plus"


def test_an_unrecorded_depth_is_unknown_rather_than_short() -> None:
    assert stack_bucket_of(0) == UNKNOWN_STACK_BUCKET
    assert stack_bucket_of(None) == UNKNOWN_STACK_BUCKET
    assert UNKNOWN_STACK_BUCKET not in DEFAULT_MTT_STACKS.labels


def test_the_bands_are_data_a_caller_can_replace() -> None:
    """#369 asks for configurable buckets, not boundaries welded into SQL."""
    custom = StackDepthBuckets(name="custom", upper_bounds=(2000,), labels=("shallow", "deep"))

    assert custom.bucket_of(1999) == "shallow"
    assert custom.bucket_of(2001) == "deep"
    assert "WHEN A.effectiveStackBB <= 2000 THEN 'shallow'" in custom.case_expression()
    assert custom.names == ("shallow", "deep", UNKNOWN_STACK_BUCKET)


@pytest.mark.parametrize(
    ("bounds", "labels", "message"),
    [
        ((1000,), ("only",), "need one more label"),
        ((2000, 1000), ("a", "b", "c"), "strictly increasing"),
        ((1000,), ("unknown", "deep"), "reserved"),
        ((1000,), ("has space", "deep"), "alphanumeric"),
    ],
)
def test_a_band_table_that_cannot_tile_its_domain_is_refused(bounds, labels, message) -> None:
    with pytest.raises(ValueError, match=message):
        StackDepthBuckets(name="bad", upper_bounds=bounds, labels=labels)


def test_mixing_shallow_and_deep_is_what_counts_as_materially_different() -> None:
    assert mixes_stack_depths({"under_10", "60_to_100"})
    assert mixes_stack_depths({"15_to_25", "25_to_40"})
    assert not mixes_stack_depths({"40_to_60", "60_to_100", "100_plus"})
    assert not mixes_stack_depths({"under_10", "10_to_15"})
    assert not mixes_stack_depths({"under_10"})
    assert not mixes_stack_depths({"under_10", UNKNOWN_STACK_BUCKET})


def test_the_band_dimension_agrees_with_the_python_one(mtt_db: Database) -> None:
    grouped = run_query(
        mtt_db,
        Query(metric="opportunities", filters={"tournament": True}, group_by=(STACK_DIMENSION,)),
    )
    cursor = mtt_db.get_cursor()
    cursor.execute("SELECT effectiveStackBB FROM HandsActions")
    expected: dict[str, int] = {}
    for (stored,) in cursor.fetchall():
        band = stack_bucket_of(stored)
        expected[band] = expected.get(band, 0) + 1

    measured = {row.group[STACK_DIMENSION]: row.opportunities for row in grouped.rows}
    assert measured == expected
    assert set(measured) <= set(STACK_DEPTH_BUCKETS)


def test_the_corpus_populates_every_band(mtt_db: Database) -> None:
    """A pack about stack depth needs a corpus that reaches every depth."""
    grouped = run_query(
        mtt_db,
        Query(metric="opportunities", filters={"tournament": True}, group_by=(STACK_DIMENSION,)),
    )
    observed = {row.group[STACK_DIMENSION] for row in grouped.rows if row.opportunities}

    assert set(DEFAULT_MTT_STACKS.labels) <= observed


# -- the pack ------------------------------------------------------------------


def test_the_explorer_has_a_tournament_entry_point() -> None:
    explorer = StudyExplorerModel(builtin_studies())
    formats = {study_format.id: study_format for study_format in explorer.formats()}

    assert set(formats) == {"cash", "tournament"}
    assert formats["tournament"].study_count == len(MTT_STUDIES)
    assert formats["tournament"].tournament is True
    spots = {
        category.id
        for category in explorer.categories("holdem", tournament=True)
        if category.study_count
    }
    assert {"preflop", "single-raised"} <= spots


def test_choosing_tournaments_hides_the_cash_studies_and_the_reverse() -> None:
    explorer = StudyExplorerModel(builtin_studies())

    tournament = explorer.studies_for_scope(tournament=True)
    cash = explorer.studies_for_scope(tournament=False)

    assert tournament and cash
    assert not {study.id for study in tournament} & {study.id for study in cash}
    assert all(study.tournament is True for study in tournament)
    assert all(study.tournament is False for study in cash)


def test_mtt_studies_are_findable_by_the_words_a_player_uses() -> None:
    explorer = StudyExplorerModel(builtin_studies())

    for term in ("MTT", "tournament", "shove", "push fold", "BB defend"):
        found = explorer.search(term, tournament=True)
        assert found, term
        assert all(study.tournament is True for study in found)


def test_the_shipped_families_cover_what_the_issue_asks_for() -> None:
    ids = {study.id for study in MTT_STUDIES}

    assert {
        "mtt_preflop_rfi",
        "mtt_preflop_facing_open",
        "mtt_preflop_facing_3bet",
        "mtt_preflop_blind_defence",
        "mtt_facing_all_in",
        "mtt_shove_spots",
    } <= ids
    assert any(study.id.startswith("mtt_srp_") for study in MTT_STUDIES)


def test_effective_stack_is_a_first_class_variable_and_breakdown() -> None:
    for study in MTT_STUDIES:
        grouped = {dimension for panel in study.panels for dimension in panel.group_by}
        assert STACK_DIMENSION in grouped, study.id
        assert STACK_DIMENSION in study.variables, study.id
        assert any(panel.kind == "hands" for panel in study.panels), study.id


def test_postflop_mtt_studies_expose_spr_as_well_as_stack() -> None:
    postflop = [study for study in MTT_STUDIES if study.path[0] == "postflop"]

    assert postflop
    for study in postflop:
        grouped = {dimension for panel in study.panels for dimension in panel.group_by}
        assert "spr_bucket" in grouped, study.id
        assert STACK_DIMENSION in grouped, study.id


def test_no_mtt_study_claims_stage_or_payout_context() -> None:
    """fpdb stores stacks, blinds and results -- not what a chip was worth."""
    forbidden = ("icm", "bubble", "final table", "payout", "pay jump", "stage")
    for study in MTT_STUDIES:
        haystack = " ".join(
            (study.title, study.description, *study.tags, *study.aliases,
             *(panel.title for panel in study.panels)),
        ).casefold()
        for word in forbidden:
            assert word not in haystack, f"{study.id} implies {word!r}"


# -- the panels, executed ------------------------------------------------------


def test_every_shipped_mtt_panel_executes_on_real_tournament_hands(mtt_db: Database) -> None:
    for study in MTT_STUDIES:
        for compiled in study.panels_compiled():
            assert compiled.available, f"{study.id}.{compiled.panel_id}"
            execute_panel(mtt_db, compiled, min_sample=0)


def test_the_shipped_mtt_studies_actually_find_their_spots(mtt_db: Database) -> None:
    empty = []
    for study in MTT_STUDIES:
        result = run_query(mtt_db, study.population_query())
        if not sum(row.opportunities for row in result.rows):
            empty.append(study.id)

    assert empty == []


def test_cash_studies_no_longer_average_tournament_hands_in(mtt_db: Database) -> None:
    """A six-max cash study is a cash study: it declares so, and excludes MTTs."""
    cash = builtin_studies().get("srp_pfr_ip_flop")

    assert cash.base_filters["tournament"] is False
    result = run_query(mtt_db, cash.population_query())
    assert sum(row.opportunities for row in result.rows) == 0


# -- Hero versus Field, and the scope warning ----------------------------------


def test_hero_and_field_keep_the_same_stack_table_and_game_scope(mtt_db: Database) -> None:
    explorer = StudyExplorerModel(builtin_studies())
    dashboard = StudyDashboardModel(explorer.open_study("mtt_preflop_rfi", remember=False))

    hero = dashboard.side_query("stack", True)
    field = dashboard.side_query("stack", False)

    assert hero.filters["tournament"] is True
    assert field.filters["tournament"] is True
    assert hero.group_by == field.group_by == (STACK_DIMENSION,)
    for name in ("game", "street", "pot_type"):
        assert hero.filters[name] == field.filters[name]
    assert sum(row.opportunities for row in run_query(mtt_db, hero).rows) > 0
    assert sum(row.opportunities for row in run_query(mtt_db, field).rows) > 0


def test_an_answer_that_averages_two_games_says_so(mtt_db: Database) -> None:
    explorer = StudyExplorerModel(builtin_studies())
    dashboard = StudyDashboardModel(explorer.open_study("mtt_shove_spots", remember=False))
    dashboard.set_active_panel("overview")

    note = dashboard.stack_depth_note(mtt_db, "overview")

    assert note is not None
    assert "averages stack depths" in note
    assert "10 BB or less" in note
    spread = dashboard.stack_depth_spread(mtt_db, "overview")
    assert mixes_stack_depths(spread)


def test_a_panel_that_breaks_down_by_stack_is_not_warned_about(mtt_db: Database) -> None:
    explorer = StudyExplorerModel(builtin_studies())
    dashboard = StudyDashboardModel(explorer.open_study("mtt_shove_spots", remember=False))

    assert dashboard.stack_depth_note(mtt_db, "stack") is None
    assert dashboard.stack_depth_note(mtt_db, "stack_position") is None


def test_narrowing_to_one_band_clears_the_warning(mtt_db: Database) -> None:
    explorer = StudyExplorerModel(builtin_studies())
    dashboard = StudyDashboardModel(explorer.open_study("mtt_shove_spots", remember=False))
    dashboard.set_active_panel("overview")
    assert dashboard.stack_depth_note(mtt_db, "overview") is not None

    dashboard.add_cross_filter(STACK_DIMENSION, "40_to_60", "40-60 BB")

    assert dashboard.stack_depth_note(mtt_db, "overview") is None


def test_a_cash_study_is_never_warned_about_tournament_depths(mtt_db: Database) -> None:
    """The check costs a query, so it only runs where it means something."""
    explorer = StudyExplorerModel(builtin_studies())
    dashboard = StudyDashboardModel(explorer.open_study("srp_pfr_ip_flop", remember=False))

    assert dashboard.stack_depth_note(mtt_db, "overview") is None


def test_a_study_opens_on_the_panel_it_declares() -> None:
    """A stack-depth pack that opens on an undifferentiated headline is useless."""
    explorer = StudyExplorerModel(builtin_studies())

    for study_id, expected in (("mtt_preflop_rfi", "stack"), ("mtt_shove_spots", "stack")):
        dashboard = StudyDashboardModel(explorer.open_study(study_id, remember=False))
        assert dashboard.state.active_panel == expected
        assert dashboard.study.default_panel == expected
