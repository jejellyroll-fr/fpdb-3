"""The PLO study pack, against a deterministic four-card corpus (#368)."""

from __future__ import annotations

import pytest

from fpdb_3_legacy.analytics_query import Query, run_query
from fpdb_3_legacy.Database import Database
from fpdb_3_legacy.hand_state import CLASSIFIED_GAMES
from fpdb_3_legacy.Importer import Importer
from fpdb_3_legacy.research_studies import (
    StudyUnavailable,
    builtin_studies,
    execute_panel,
    panel_unavailable_reason,
)
from fpdb_3_legacy.research_study_dashboard import StudyDashboardModel
from fpdb_3_legacy.research_study_explorer import StudyExplorerModel
from fpdb_3_legacy.spr_buckets import SPR_BUCKETS, spr_bucket_of
from tests.helpers import plo_golden as plo

_IMPORTERS: list[Importer] = []
PLO_STUDIES = tuple(
    study for study in builtin_studies().studies if study.game == plo.PLO_GAME
)


@pytest.fixture(scope="module")
def plo_db(tmp_path_factory) -> Database:
    config = plo.build_config(tmp_path_factory.mktemp("plo-studies"))
    database = Database(config)
    database.recreate_tables()
    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=config, sql=None)
    importer.database = database
    for path in plo.plo_files():
        importer.addImportFile(str(path), "PokerStars")
    importer.runImport()
    _IMPORTERS.append(importer)
    return database


# -- the corpus ----------------------------------------------------------------


def test_the_corpus_is_four_card_omaha_and_nothing_else(plo_db: Database) -> None:
    cursor = plo_db.get_cursor()
    cursor.execute(
        "SELECT G.category, COUNT(*) FROM Hands H JOIN Gametypes G ON G.id = H.gametypeId"
        " GROUP BY G.category",
    )

    assert cursor.fetchall() == [(plo.PLO_GAME, len(plo.plo_files()))]


def test_the_corpus_reaches_the_pot_types_the_pack_studies(plo_db: Database) -> None:
    cursor = plo_db.get_cursor()
    cursor.execute("SELECT DISTINCT potType FROM HandsSituations")
    pot_types = {row[0] for row in cursor.fetchall()}

    assert {"unopened", "single_raised", "three_bet"} <= pot_types


# -- the pack ------------------------------------------------------------------


def test_the_pack_ships_a_plo_hierarchy_rather_than_only_holdem() -> None:
    explorer = StudyExplorerModel(builtin_studies())
    games = {game.id: game for game in explorer.games()}

    assert plo.PLO_GAME in games
    assert games[plo.PLO_GAME].label == "Pot-Limit Omaha"
    assert games[plo.PLO_GAME].study_count >= 10
    spots = {
        category.id
        for category in explorer.categories(plo.PLO_GAME)
        if category.study_count
    }
    assert {"preflop", "single-raised", "three-bet-pot"} <= spots


def test_choosing_omaha_hides_the_holdem_studies_and_the_reverse() -> None:
    explorer = StudyExplorerModel(builtin_studies())

    omaha = explorer.studies_for_game(plo.PLO_GAME)
    holdem = explorer.studies_for_game("holdem")

    assert omaha and holdem
    assert not {study.id for study in omaha} & {study.id for study in holdem}
    assert all(study.game == plo.PLO_GAME for study in omaha)


def test_plo_studies_are_findable_by_the_words_a_player_uses() -> None:
    explorer = StudyExplorerModel(builtin_studies())

    for term in ("PLO", "Omaha", "pot-limit Omaha", "3bet pot"):
        found = explorer.search(term, game=plo.PLO_GAME)
        assert found, term
        assert all(study.game == plo.PLO_GAME for study in found)


def test_no_plo_study_ships_a_holdem_only_panel() -> None:
    for study in PLO_STUDIES:
        for panel in study.panels:
            assert panel.kind != "range_grid", f"{study.id}.{panel.id}"
            assert not panel.holdem_only, f"{study.id}.{panel.id}"


def test_plo_studies_emphasise_spr_multiway_board_and_sizing() -> None:
    postflop = [study for study in PLO_STUDIES if study.path[0] == "postflop"]

    assert postflop
    for study in postflop:
        grouped = {dimension for panel in study.panels for dimension in panel.group_by}
        assert "spr_bucket" in grouped, study.id
        assert "multiway" in grouped, study.id
        assert {"board_suit", "board_pairing"} <= grouped, study.id
        assert "board_connectivity" in grouped, study.id
        assert grouped & {"sizing_bucket", "facing_sizing_bucket"}, study.id
        assert "stack_bucket" in grouped, study.id


def test_every_plo_study_keeps_its_source_hands() -> None:
    for study in PLO_STUDIES:
        assert any(panel.kind == "hands" for panel in study.panels), study.id


# -- what PLO must not claim ---------------------------------------------------


def test_a_hand_strength_panel_is_refused_for_a_game_the_classifier_cannot_read() -> None:
    strength = next(
        panel
        for study in builtin_studies().studies
        if study.game == "holdem"
        for panel in study.panels
        if panel.kind == "hand_strength"
    )

    assert panel_unavailable_reason(strength, "holdem") is None
    reason = panel_unavailable_reason(strength, plo.PLO_GAME)
    assert reason is not None
    assert "classifier" in reason
    assert "best two cards" in reason
    assert plo.PLO_GAME not in CLASSIFIED_GAMES


def test_a_range_grid_is_refused_for_omaha_and_says_why() -> None:
    grid = next(
        panel
        for study in builtin_studies().studies
        if study.game == "holdem"
        for panel in study.panels
        if panel.kind == "range_grid"
    )

    reason = panel_unavailable_reason(grid, plo.PLO_GAME)
    assert reason is not None
    assert "two hole cards" in reason
    assert "Hold'em-only" in reason


def test_an_unavailable_panel_refuses_to_execute_rather_than_answering(plo_db: Database) -> None:
    holdem_study = next(
        study
        for study in builtin_studies().studies
        if study.game == "holdem" and any(panel.kind == "range_grid" for panel in study.panels)
    )
    grid = holdem_study.panel(
        next(panel.id for panel in holdem_study.panels if panel.kind == "range_grid"),
    )
    omaha_grid = type(grid)(**{**grid.__dict__, "unavailable_reason": "test"})

    with pytest.raises(StudyUnavailable):
        execute_panel(plo_db, omaha_grid)


def test_a_study_that_declares_no_game_is_not_disabled_on_a_guess() -> None:
    grid = next(
        panel
        for study in builtin_studies().studies
        if study.game == "holdem"
        for panel in study.panels
        if panel.kind == "range_grid"
    )

    assert panel_unavailable_reason(grid, None) is None


# -- the panels, executed ------------------------------------------------------


def test_every_shipped_plo_panel_executes_on_real_omaha_hands(plo_db: Database) -> None:
    for study in PLO_STUDIES:
        for compiled in study.panels_compiled():
            assert compiled.available, f"{study.id}.{compiled.panel_id}"
            execute_panel(plo_db, compiled, min_sample=0)


def test_the_shipped_plo_studies_actually_find_their_spots(plo_db: Database) -> None:
    """A study whose population is always empty is a study nobody can use."""
    empty = []
    for study in PLO_STUDIES:
        result = run_query(plo_db, study.population_query())
        if not sum(row.opportunities for row in result.rows):
            empty.append(study.id)

    assert empty == []


def test_hero_and_field_both_have_plo_decisions_to_compare(plo_db: Database) -> None:
    explorer = StudyExplorerModel(builtin_studies())
    dashboard = StudyDashboardModel(explorer.open_study("plo_srp_pfr_ip_flop", remember=False))

    hero = run_query(plo_db, dashboard.side_query("overview", True))
    field = run_query(plo_db, dashboard.side_query("overview", False))

    assert sum(row.opportunities for row in hero.rows) > 0
    assert sum(row.opportunities for row in field.rows) > 0


def test_a_plo_dashboard_drills_into_both_sides_of_its_population() -> None:
    explorer = StudyExplorerModel(builtin_studies())
    dashboard = StudyDashboardModel(explorer.open_study("plo_3bet_defender_flop", remember=False))

    context = dashboard.drill_context("overview")

    assert context.sides_agree()
    assert context.side_query("hero").filters["game"] == plo.PLO_GAME


# -- the SPR band --------------------------------------------------------------


def test_spr_bands_group_the_stored_ratio_the_way_a_player_reads_it() -> None:
    assert spr_bucket_of(0) == "unknown"
    assert spr_bucket_of(None) == "unknown"
    assert spr_bucket_of(50) == "under_1"
    assert spr_bucket_of(100) == "1_to_2"
    assert spr_bucket_of(399) == "2_to_4"
    assert spr_bucket_of(699) == "4_to_7"
    assert spr_bucket_of(1299) == "7_to_13"
    assert spr_bucket_of(1300) == "13_plus"


def test_the_spr_band_dimension_agrees_with_the_python_one(plo_db: Database) -> None:
    grouped = run_query(
        plo_db,
        Query(
            metric="opportunities",
            filters={"game": plo.PLO_GAME, "street": "flop"},
            group_by=("spr_bucket",),
        ),
    )
    cursor = plo_db.get_cursor()
    cursor.execute(
        "SELECT A.sprBefore FROM HandsActions A"
        " JOIN HandsSituations SI ON SI.handId = A.handId AND SI.actionNo = A.actionNo"
        " WHERE SI.streetName = 'flop'",
    )
    expected: dict[str, int] = {}
    for (stored,) in cursor.fetchall():
        bucket = spr_bucket_of(stored)
        expected[bucket] = expected.get(bucket, 0) + 1

    measured = {row.group["spr_bucket"]: row.opportunities for row in grouped.rows}
    assert measured == expected
    assert set(measured) <= set(SPR_BUCKETS)


def test_a_three_bet_pot_lands_in_a_lower_spr_band_than_a_single_raised_one(plo_db: Database) -> None:
    def bands(pot_type: str) -> set[str]:
        result = run_query(
            plo_db,
            Query(
                metric="opportunities",
                filters={"game": plo.PLO_GAME, "street": "flop", "pot_type": pot_type},
                group_by=("spr_bucket",),
            ),
        )
        return {row.group["spr_bucket"] for row in result.rows if row.opportunities}

    single = bands("single_raised")
    three = bands("three_bet")

    assert single and three
    order = list(SPR_BUCKETS)
    assert min(order.index(band) for band in three) < max(order.index(band) for band in single)
