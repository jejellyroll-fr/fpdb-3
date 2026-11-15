"""Shared PLO studies against imported four- and five-card hands."""

from __future__ import annotations

from dataclasses import replace

import pytest

from fpdb_3_legacy.analytics_query import run_query
from fpdb_3_legacy.Database import Database
from fpdb_3_legacy.Importer import Importer
from fpdb_3_legacy.research_browser import run_drill_down
from fpdb_3_legacy.research_drilldown import run_side_drill
from fpdb_3_legacy.research_studies import StudySpec, StudyValidationError, builtin_studies, execute_panel
from fpdb_3_legacy.research_study_dashboard import StudyDashboardModel
from fpdb_3_legacy.research_study_explorer import StudyExplorerModel
from tests.helpers import analytics_golden as holdem
from tests.helpers import plo_golden as plo

GAMES = ["omahahi", "5_omahahi"]
PLO_STUDIES = tuple(study for study in builtin_studies().studies if study.game == "omahahi")
_IMPORTERS: list[Importer] = []


@pytest.fixture(scope="module")
def mixed_db(tmp_path_factory) -> Database:
    directory = tmp_path_factory.mktemp("plo5-studies")
    config = plo.build_config(directory)
    db = Database(config)
    db.recreate_tables()
    importer = Importer(caller=None, settings={"testData": False, "threads": 1}, config=config, sql=None)
    importer.database = db
    for path in [*plo.plo_files(), *plo.five_card_files(directory / "five-card"), holdem.golden_files()[0]]:
        importer.addImportFile(str(path), "PokerStars")
    importer.runImport()
    _IMPORTERS.append(importer)
    return db


def test_both_variants_offer_the_same_studies_without_duplicating_the_library(tmp_path) -> None:
    explorer = StudyExplorerModel(state_path=tmp_path / "history.json")
    four = explorer.studies_for_game(GAMES[0])
    five = explorer.studies_for_game(GAMES[1])
    assert four == five == PLO_STUDIES
    assert explorer.categories(GAMES[0]) == explorer.categories(GAMES[1])
    games = {game.id: game for game in explorer.games()}
    assert games[GAMES[0]].label == "Pot-Limit Omaha 4c"
    assert games[GAMES[1]].label == "Pot-Limit Omaha 5c"
    assert games[GAMES[0]].study_count == games[GAMES[1]].study_count == len(PLO_STUDIES)
    assert not {study.id for study in explorer.studies_for_game("holdem")} & {study.id for study in five}
    assert explorer.search("PLO5", game=GAMES[1]) == PLO_STUDIES


@pytest.mark.parametrize("game", [None, "any", *GAMES])
def test_scope_survives_every_panel_variables_comparison_and_drilldown(tmp_path, game) -> None:
    explorer = StudyExplorerModel(state_path=tmp_path / "history.json")
    selection = explorer.open_study("plo_srp_pfr_ip_flop", context_filters={"game": game}, remember=False)
    assert selection.available
    expected = GAMES if game in (None, "any") else game
    dashboard = StudyDashboardModel(selection)
    dashboard.set_variable("position", "co")
    for panel in dashboard.study.panels:
        assert dashboard.panel_query(panel.id).filters["game"] == expected
        assert dashboard.side_query(panel.id, True).filters["game"] == expected
        assert dashboard.side_query(panel.id, False).filters["game"] == expected
    dashboard.add_cross_filter("board_pairing", "unpaired")
    context = dashboard.drill_context("overview")
    assert context.sides_agree()
    for side in ("hero", "field"):
        assert context.side_query(side).filters["game"] == expected
        assert context.side_query(side).filters["board_pairing"] == "unpaired"


@pytest.mark.parametrize("game", ["holdem", "omahahilo", "6_omahahi", ["5_omahahi", "holdem"]])
def test_context_cannot_expand_a_plo_study_to_other_games(tmp_path, game) -> None:
    explorer = StudyExplorerModel(state_path=tmp_path / "history.json")
    selection = explorer.open_study("plo_preflop_rfi", context_filters={"game": game}, remember=False)
    assert not selection.available
    assert selection.unavailable_reason
    assert explorer.history.recent == []


def test_supported_games_round_trip_and_population_validation() -> None:
    original = PLO_STUDIES[0]
    restored = StudySpec.from_mapping(original.as_dict())
    assert restored == original
    assert restored.games == tuple(GAMES)
    assert replace(restored, base_filters={**restored.base_filters, "game": GAMES[1]}).panel("overview").available
    for filters in ({"game": "holdem"}, {}):
        with pytest.raises(StudyValidationError, match="conflicts"):
            replace(restored, base_filters=filters)
    with pytest.raises(StudyValidationError, match="conflicts"):
        replace(restored, game="holdem")


def test_holdem_panels_stay_unavailable_for_both_omaha_variants() -> None:
    for study in PLO_STUDIES:
        for panel in study.panels:
            assert panel.kind not in {"range_grid", "hand_strength"}
            assert not panel.holdem_only
    holdem_study = builtin_studies().get("srp_pfr_ip_flop")
    # Checking every supported game also protects future mixed study packs.
    mixed = replace(holdem_study, supported_games=("holdem", "5_omahahi"))
    for panel in mixed.panels:
        if panel.kind in {"range_grid", "hand_strength"}:
            assert not mixed.panel(panel.id).available


def test_mixed_corpus_imports_all_hands_under_their_actual_variants(mixed_db) -> None:
    cursor = mixed_db.get_cursor()
    cursor.execute("SELECT G.category, COUNT(*) FROM Hands H JOIN Gametypes G ON G.id = H.gametypeId GROUP BY G.category")
    assert dict(cursor.fetchall()) == {"holdem": 1, "omahahi": len(plo.plo_files()), "5_omahahi": len(plo.plo_files())}


def test_each_study_combines_both_variants_and_each_explicit_filter_isolates_one(mixed_db, tmp_path) -> None:
    explorer = StudyExplorerModel(state_path=tmp_path / "history.json")
    for study in PLO_STUDIES:
        populations = []
        for game in [None, *GAMES]:
            selection = explorer.open_study(study.id, context_filters={"game": game}, remember=False)
            dashboard = StudyDashboardModel(selection)
            compiled = dashboard.panel("overview")
            result = run_query(mixed_db, replace(compiled.query, group_by=("game",)))
            counts = {row.group["game"]: row.opportunities for row in result.rows}
            assert set(counts) == (set(GAMES) if game is None else {game}), study.id
            assert all(count > 0 for count in counts.values()), study.id
            populations.append(sum(counts.values()))
            for panel_id in dashboard.panel_ids():
                panel = dashboard.panel(panel_id)
                assert panel.available
                execute_panel(mixed_db, panel, min_sample=0)
        assert populations[0] == populations[1] + populations[2], study.id


@pytest.mark.parametrize("game,card_count", [("omahahi", 4), ("5_omahahi", 5)])
def test_source_hands_show_all_cards_for_hero_field_and_legacy_drill(mixed_db, tmp_path, game, card_count) -> None:
    explorer = StudyExplorerModel(state_path=tmp_path / "history.json")
    selection = explorer.open_study("plo_preflop_facing_open", context_filters={"game": game}, remember=False)
    dashboard = StudyDashboardModel(selection)
    context = dashboard.drill_context("overview")
    for side in ("hero", "field"):
        page = run_side_drill(mixed_db, context, side, limit=200)
        assert page.known_cards > 0
        assert all(row["category"] == game for row in page.rows)
        assert all(len(row["playerCards"]) == card_count * 2 for row in page.rows if row["playerCards"])
        if side == "field":
            assert page.unknown_cards > 0
    legacy = run_drill_down(mixed_db, dashboard.panel_query("overview"), limit=200)
    assert legacy.rows
    assert all(len(row["heroCards"]) == card_count * 2 for row in legacy.rows)
